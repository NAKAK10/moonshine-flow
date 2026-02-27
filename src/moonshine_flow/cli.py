"""CLI entrypoint for moonshine-flow."""

from __future__ import annotations

import argparse
import logging
import os
import platform
import sys
from importlib.metadata import PackageNotFoundError, version as package_version
from importlib.util import find_spec
from pathlib import Path

from moonshine_flow.app_bundle import default_app_bundle_path, install_app_bundle_from_env
from moonshine_flow.config import default_config_path, load_config
from moonshine_flow.launchd import (
    LAUNCH_AGENT_LABEL,
    install_launch_agent,
    launch_agent_log_paths,
    launch_agent_path,
    read_launch_agent_plist,
    uninstall_launch_agent,
)
from moonshine_flow.logging_setup import configure_logging
from moonshine_flow.permissions import (
    check_all_permissions,
    check_permissions_in_launchd_context,
    format_permission_guidance,
    recommended_permission_target,
    request_accessibility_permission,
    request_input_monitoring_permission,
    request_microphone_permission,
    request_all_permissions,
)

LOGGER = logging.getLogger(__name__)


def _resolve_app_version() -> str:
    try:
        return package_version("moonshine-flow")
    except PackageNotFoundError:
        return "0.0.0.dev0"


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
    in_launchd_context = os.environ.get("XPC_SERVICE_NAME") == LAUNCH_AGENT_LABEL
    if in_launchd_context and not report.all_granted:
        # Trigger prompts from daemon context so launchd-triggered runs can obtain trust.
        if not report.microphone:
            request_microphone_permission()
        if not report.accessibility:
            request_accessibility_permission()
        if not report.input_monitoring:
            request_input_monitoring_permission()
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
    if getattr(args, "install_app_bundle", True):
        bundle_path = install_app_bundle_from_env()
        if bundle_path is not None:
            print(f"Installed app bundle: {bundle_path}")
            print(
                "Note: macOS permissions are still managed by user action in "
                "System Settings -> Privacy & Security."
            )

    permission_report = (
        request_all_permissions() if args.request_permissions else check_all_permissions()
    )
    if not permission_report.all_granted:
        guidance = format_permission_guidance(permission_report)
        if not args.allow_missing_permissions:
            print(guidance, file=sys.stderr)
            print(
                "\nLaunch agent installation was aborted because missing permissions can "
                "prevent hotkey detection and paste output.",
                file=sys.stderr,
            )
            print(
                "Retry after granting permissions, or run with "
                "`--allow-missing-permissions` to install anyway.",
                file=sys.stderr,
            )
            return 2

        print(
            "Warning: continuing with missing permissions because "
            "`--allow-missing-permissions` was specified.",
            file=sys.stderr,
        )
        print(guidance, file=sys.stderr)

    plist_path = install_launch_agent(config_path)
    print(f"Installed launch agent: {plist_path}")
    print(f"Permission target (recommended): {recommended_permission_target()}")
    return 0


def cmd_uninstall_launch_agent(args: argparse.Namespace) -> int:
    del args
    removed = uninstall_launch_agent()
    if removed:
        print(f"Removed launch agent: {launch_agent_path()}")
    else:
        print("Launch agent is not installed.")
    return 0


def cmd_install_app_bundle(args: argparse.Namespace) -> int:
    app_path = Path(args.path).expanduser() if args.path else default_app_bundle_path()
    installed = install_app_bundle_from_env(app_path)
    if installed is None:
        print(
            "App bundle install is unavailable in this context. "
            "Run this via Homebrew-installed `mflow`.",
            file=sys.stderr,
        )
        return 2
    print(f"Installed app bundle: {installed}")
    return 0


def _derive_launchd_permission_check_command(
    launchd_payload: dict[str, object] | None,
) -> list[str]:
    """Resolve a check-permissions command that matches launchd runtime context."""
    default_command = ["mflow", "check-permissions"]
    if not isinstance(launchd_payload, dict):
        return default_command

    program_args = launchd_payload.get("ProgramArguments")
    if not isinstance(program_args, list) or not program_args:
        return default_command

    resolved_parts = [str(part) for part in program_args]
    if "run" in resolved_parts:
        run_index = resolved_parts.index("run")
        prefix = resolved_parts[:run_index]
        if prefix:
            return [*prefix, "check-permissions"]

    if resolved_parts:
        return [resolved_parts[0], "check-permissions"]
    return default_command


def _latest_launchd_runtime_warning(err_log_path: Path) -> str | None:
    """Return latest launchd runtime warning text from daemon stderr log when present."""
    if not err_log_path.exists():
        return None
    try:
        lines = err_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if not lines:
        return None

    latest_start = 0
    for idx, line in enumerate(lines):
        if "Moonshine Flow daemon starting" in line:
            latest_start = idx

    recent = lines[latest_start:]
    if any("This process is not trusted!" in line for line in recent):
        return "pynput listener is not trusted in daemon runtime context"
    if any("Missing macOS permissions detected:" in line for line in recent):
        return "daemon runtime detected missing macOS permissions"
    return None


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
    print(f"Permission target (recommended): {recommended_permission_target()}")
    launchd_payload = read_launch_agent_plist()
    out_log_path, err_log_path = launch_agent_log_paths()
    if launchd_payload is None:
        print(f"LaunchAgent plist: MISSING ({launch_agent_path()})")
        print("Install LaunchAgent: mflow install-launch-agent")
    else:
        print(f"LaunchAgent plist: FOUND ({launch_agent_path()})")
        print(f"LaunchAgent label: {launchd_payload.get('Label', 'UNKNOWN')}")
        program_args = launchd_payload.get("ProgramArguments")
        if isinstance(program_args, list) and program_args:
            print(f"LaunchAgent program: {' '.join(str(part) for part in program_args)}")
        else:
            print("LaunchAgent program: UNKNOWN")
    print(f"Daemon stdout log: {out_log_path}")
    print(f"Daemon stderr log: {err_log_path}")
    runtime_warning = _latest_launchd_runtime_warning(err_log_path)
    if runtime_warning:
        print(f"Launchd runtime status: WARNING ({runtime_warning})")

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

    if getattr(args, "launchd_check", False):
        launchd_command = _derive_launchd_permission_check_command(launchd_payload)
        probe = check_permissions_in_launchd_context(command=launchd_command)
        if probe.report is not None:
            launchd_report = probe.report
            print("Launchd permissions:", "OK" if launchd_report.all_granted else "INCOMPLETE")
            if not launchd_report.all_granted:
                print(f"Launchd missing permissions: {', '.join(launchd_report.missing)}")
            if set(launchd_report.missing) != set(report.missing):
                print(
                    "Permission mismatch detected between terminal and launchd contexts. "
                    "Grant permissions for the recommended target above."
                )
            if runtime_warning:
                print(
                    "Launchd runtime log indicates trust failure despite check output. "
                    "Restart the launch agent after granting permissions."
                )
        else:
            print("Launchd permissions: ERROR")
            if probe.error:
                print(f"Launchd check error: {probe.error}")
            if probe.stderr:
                print(f"Launchd check stderr: {probe.stderr}")

    if platform.system() == "Darwin" and os_machine == "arm64" and py_machine != "arm64":
        print(
            "\nWarning: Apple Silicon macOS is running an x86_64 Python environment "
            "(likely Rosetta). Moonshine packages may be unavailable. "
            "Use an arm64 Python interpreter."
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="moonshine-flow")
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {_resolve_app_version()}",
    )
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
    doctor_parser.add_argument(
        "--launchd-check",
        action="store_true",
        help="Compare permission status in launchd context via launchctl asuser",
    )
    doctor_parser.set_defaults(func=cmd_doctor)

    install_parser = subparsers.add_parser("install-launch-agent", help="Install launchd agent")
    install_parser.add_argument("--config", default=None, help="Path to config TOML")
    install_parser.add_argument(
        "--request-permissions",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Request missing macOS permissions before installing launchd agent",
    )
    install_parser.add_argument(
        "--allow-missing-permissions",
        action="store_true",
        help="Install launchd agent even when required macOS permissions are missing",
    )
    install_parser.add_argument(
        "--verbose-bootstrap",
        action="store_true",
        help="Show detailed runtime bootstrap logs when recovery runs",
    )
    install_parser.add_argument(
        "--install-app-bundle",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Create/update ~/Applications/MoonshineFlow.app before installing launchd agent",
    )
    install_parser.set_defaults(func=cmd_install_launch_agent)

    uninstall_parser = subparsers.add_parser("uninstall-launch-agent", help="Remove launchd agent")
    uninstall_parser.set_defaults(func=cmd_uninstall_launch_agent)

    app_bundle_parser = subparsers.add_parser(
        "install-app-bundle",
        help="Create or update ~/Applications/MoonshineFlow.app from current runtime",
    )
    app_bundle_parser.add_argument(
        "--path",
        default=None,
        help="Custom .app destination path (default: ~/Applications/MoonshineFlow.app)",
    )
    app_bundle_parser.set_defaults(func=cmd_install_app_bundle)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
