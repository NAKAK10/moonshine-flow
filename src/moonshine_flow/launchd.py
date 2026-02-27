"""launchd integration for login auto-start."""

from __future__ import annotations

import json
import plistlib
import shutil
import subprocess
import sys
import time
from pathlib import Path

from moonshine_flow.app_bundle import resolve_launch_agent_app_command

LAUNCH_AGENT_LABEL = "com.moonshineflow.daemon"
RESTART_PERMISSION_SUPPRESSION_TTL_SECONDS = 30


def launch_agent_path() -> Path:
    """Path to user LaunchAgent plist."""
    return Path("~/Library/LaunchAgents/com.moonshineflow.daemon.plist").expanduser()


def launch_agent_log_paths() -> tuple[Path, Path]:
    """Expected daemon log file locations."""
    log_dir = Path("~/Library/Logs/moonshine-flow").expanduser()
    return (log_dir / "daemon.out.log", log_dir / "daemon.err.log")


def launch_agent_restart_suppression_path() -> Path:
    """Path to one-shot marker that suppresses permission prompts after restart."""
    return (
        Path("~/Library/Application Support/moonshine-flow").expanduser()
        / "restart-suppression.json"
    )


def mark_restart_permission_suppression(
    ttl_seconds: int = RESTART_PERMISSION_SUPPRESSION_TTL_SECONDS,
) -> None:
    """Write one-shot marker used to suppress launchd prompt requests right after restart."""
    marker_path = launch_agent_restart_suppression_path()
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    expires_at = time.time() + max(ttl_seconds, 0)
    payload = {"expires_at": expires_at}
    marker_path.write_text(json.dumps(payload), encoding="utf-8")


def clear_restart_permission_suppression() -> None:
    """Remove suppression marker file when present."""
    launch_agent_restart_suppression_path().unlink(missing_ok=True)


def consume_restart_permission_suppression() -> bool:
    """Consume suppression marker and return whether it is still active."""
    marker_path = launch_agent_restart_suppression_path()
    if not marker_path.exists():
        return False

    try:
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
        expires_at = float(payload.get("expires_at", 0))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        clear_restart_permission_suppression()
        return False

    clear_restart_permission_suppression()
    return time.time() <= expires_at


def read_launch_agent_plist() -> dict[str, object] | None:
    """Read installed LaunchAgent plist when present."""
    plist_path = launch_agent_path()
    if not plist_path.exists():
        return None
    try:
        with plist_path.open("rb") as fp:
            payload = plistlib.load(fp)
    except (OSError, plistlib.InvalidFileException):
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _launchctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["launchctl", *args], text=True, capture_output=True, check=False)


def _resolve_daemon_command() -> list[str]:
    """Resolve command used by LaunchAgent to run the daemon."""
    app_command = resolve_launch_agent_app_command()
    if app_command:
        return app_command

    for candidate in ("mflow", "moonshine-flow"):
        resolved = shutil.which(candidate)
        if resolved:
            return [resolved]
    return [sys.executable, "-m", "moonshine_flow.cli"]


def resolve_launch_agent_program_prefix() -> list[str]:
    """Resolve launch-agent command prefix before CLI subcommand arguments."""
    return _resolve_daemon_command()


def build_launch_agent(config_path: Path) -> dict[str, object]:
    """Build LaunchAgent plist data."""
    stdout_path, stderr_path = launch_agent_log_paths()
    stdout_path.parent.mkdir(parents=True, exist_ok=True)

    program_args = [
        *resolve_launch_agent_program_prefix(),
        "run",
        "--config",
        str(config_path),
    ]

    return {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": program_args,
        "RunAtLoad": True,
        "KeepAlive": False,
        "StandardOutPath": str(stdout_path),
        "StandardErrorPath": str(stderr_path),
        "ProcessType": "Interactive",
    }


def install_launch_agent(config_path: Path) -> Path:
    """Install or replace launchd plist and bootstrap it."""
    plist_path = launch_agent_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    data = build_launch_agent(config_path)
    with plist_path.open("wb") as fp:
        plistlib.dump(data, fp)

    uid = str(subprocess.check_output(["id", "-u"], text=True).strip())
    _launchctl("bootout", f"gui/{uid}", str(plist_path))
    boot = _launchctl("bootstrap", f"gui/{uid}", str(plist_path))
    if boot.returncode != 0:
        raise RuntimeError(f"launchctl bootstrap failed: {boot.stderr.strip()}")

    return plist_path


def uninstall_launch_agent() -> bool:
    """Unload and remove launchd plist if present."""
    plist_path = launch_agent_path()
    if not plist_path.exists():
        return False

    uid = str(subprocess.check_output(["id", "-u"], text=True).strip())
    _launchctl("bootout", f"gui/{uid}", str(plist_path))
    plist_path.unlink(missing_ok=True)
    return True


def restart_launch_agent() -> bool:
    """Restart installed launchd agent after permission changes."""
    plist_path = launch_agent_path()
    if not plist_path.exists():
        return False

    uid = str(subprocess.check_output(["id", "-u"], text=True).strip())
    service = f"gui/{uid}/{LAUNCH_AGENT_LABEL}"
    mark_restart_permission_suppression()
    try:
        kick = _launchctl("kickstart", "-k", service)
        if kick.returncode == 0:
            return True

        _launchctl("bootout", f"gui/{uid}", str(plist_path))
        boot = _launchctl("bootstrap", f"gui/{uid}", str(plist_path))
        if boot.returncode != 0:
            detail = kick.stderr.strip() or boot.stderr.strip()
            raise RuntimeError(f"launchctl restart failed: {detail}")
        return True
    except Exception:
        clear_restart_permission_suppression()
        raise
