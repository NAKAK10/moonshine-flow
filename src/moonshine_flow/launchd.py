"""launchd integration for login auto-start."""

from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path

LAUNCH_AGENT_LABEL = "com.moonshineflow.daemon"


def launch_agent_path() -> Path:
    """Path to user LaunchAgent plist."""
    return Path("~/Library/LaunchAgents/com.moonshineflow.daemon.plist").expanduser()


def launch_agent_log_paths() -> tuple[Path, Path]:
    """Expected daemon log file locations."""
    log_dir = Path("~/Library/Logs/moonshine-flow").expanduser()
    return (log_dir / "daemon.out.log", log_dir / "daemon.err.log")


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


def build_launch_agent(config_path: Path) -> dict[str, object]:
    """Build LaunchAgent plist data."""
    stdout_path, stderr_path = launch_agent_log_paths()
    stdout_path.parent.mkdir(parents=True, exist_ok=True)

    program_args = [
        sys.executable,
        "-m",
        "moonshine_flow.cli",
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
        "ProcessType": "Background",
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
