"""CLI entrypoint for moonshine-flow."""

from __future__ import annotations

import argparse
import logging
import os
import platform
import sys
from importlib.util import find_spec
from pathlib import Path

from moonshine_flow.config import default_config_path, load_config
from moonshine_flow.launchd import install_launch_agent, launch_agent_path, uninstall_launch_agent
from moonshine_flow.logging_setup import configure_logging
from moonshine_flow.permissions import (
    check_all_permissions,
    format_permission_guidance,
    request_all_permissions,
)

LOGGER = logging.getLogger(__name__)


def _resolve_config_path(path_value: str | None) -> Path:
    if path_value:
        return Path(path_value).expanduser()
    return default_config_path()


def _has_moonshine_backend() -> bool:
    return bool(find_spec("moonshine_voice"))


def _backend_guidance() -> str:
    return (
        "Moonshine backend package is missing. "
        "Install dependencies and run `uv sync` again."
    )


def cmd_run(args: argparse.Namespace) -> int:
    from moonshine_flow.daemon import MoonshineFlowDaemon

    config_path = _resolve_config_path(args.config)
    config = load_config(config_path)
    configure_logging(config.runtime.log_level)

    if not _has_moonshine_backend():
        LOGGER.error(_backend_guidance())
        return 3

    report = check_all_permissions()
    if not report.all_granted:
        LOGGER.warning(format_permission_guidance(report))

    daemon = MoonshineFlowDaemon(config)
    try:
        backend = daemon.transcriber.preflight_model()
        LOGGER.info("Model preflight OK (%s)", backend)
    except Exception as exc:
        LOGGER.error("Model preflight failed: %s", exc)
        if "incompatible architecture" in str(exc).lower():
            LOGGER.error(
                "Detected architecture mismatch between Python runtime and Moonshine binaries. "
                "Run `moonshine-flow doctor` and ensure arm64 python@3.11 + uv are available on "
                "Apple Silicon (typically under /opt/homebrew)."
            )
        return 4

    try:
        daemon.run_forever()
    except KeyboardInterrupt:
        LOGGER.info("Interrupted by user")
    finally:
        daemon.stop()
    return 0


def cmd_check_permissions(args: argparse.Namespace) -> int:
    report = request_all_permissions() if args.request else check_all_permissions()
    print("Microphone:", "OK" if report.microphone else "MISSING")
    print("Accessibility:", "OK" if report.accessibility else "MISSING")
    print("Input Monitoring:", "OK" if report.input_monitoring else "MISSING")

    if report.all_granted:
        print("\nAll required permissions are granted.")
        return 0

    print("\n" + format_permission_guidance(report))
    if not args.request:
        print(
            "\nTip: run `uv run moonshine-flow check-permissions --request` "
            "once to trigger prompts."
        )
    return 2


def cmd_install_launch_agent(args: argparse.Namespace) -> int:
    config_path = _resolve_config_path(args.config)
    load_config(config_path)
    plist_path = install_launch_agent(config_path)
    print(f"Installed launch agent: {plist_path}")
    return 0


def cmd_uninstall_launch_agent(args: argparse.Namespace) -> int:
    del args
    removed = uninstall_launch_agent()
    if removed:
        print(f"Removed launch agent: {launch_agent_path()}")
    else:
        print("Launch agent is not installed.")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from moonshine_flow.transcriber import MoonshineTranscriber

    config_path = _resolve_config_path(args.config)
    config = load_config(config_path)

    os_machine = os.uname().machine if hasattr(os, "uname") else "unknown"
    py_machine = platform.machine()

    print(f"Platform: {platform.platform()}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"OS machine: {os_machine}")
    print(f"Python machine: {py_machine}")
    print(f"Config: {config_path}")

    for pkg in ("moonshine_voice", "sounddevice", "pynput"):
        print(f"Package {pkg}:", "FOUND" if find_spec(pkg) else "MISSING")

    if not _has_moonshine_backend():
        print(_backend_guidance())

    transcriber = MoonshineTranscriber(
        model_size=config.model.size.value,
        language=config.model.language,
        device=config.model.device,
    )
    print("Transcriber:", transcriber.backend_summary())

    report = check_all_permissions()
    print("Permissions:", "OK" if report.all_granted else "INCOMPLETE")
    if not report.all_granted:
        print(format_permission_guidance(report))

    if platform.system() == "Darwin" and os_machine == "arm64" and py_machine != "arm64":
        print(
            "\nWarning: Apple Silicon macOS is running an x86_64 Python environment "
            "(likely Rosetta). Moonshine packages may be unavailable. "
            "Use an arm64 Python interpreter."
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="moonshine-flow")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run background daemon")
    run_parser.add_argument("--config", default=None, help="Path to config TOML")
    run_parser.set_defaults(func=cmd_run)

    check_parser = subparsers.add_parser("check-permissions", help="Check macOS permissions")
    check_parser.add_argument(
        "--request",
        action="store_true",
        help="Request missing macOS permissions (shows system prompts when possible)",
    )
    check_parser.set_defaults(func=cmd_check_permissions)

    doctor_parser = subparsers.add_parser("doctor", help="Show runtime diagnostics")
    doctor_parser.add_argument("--config", default=None, help="Path to config TOML")
    doctor_parser.set_defaults(func=cmd_doctor)

    install_parser = subparsers.add_parser("install-launch-agent", help="Install launchd agent")
    install_parser.add_argument("--config", default=None, help="Path to config TOML")
    install_parser.set_defaults(func=cmd_install_launch_agent)

    uninstall_parser = subparsers.add_parser("uninstall-launch-agent", help="Remove launchd agent")
    uninstall_parser.set_defaults(func=cmd_uninstall_launch_agent)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
