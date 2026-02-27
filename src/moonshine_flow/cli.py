"""CLI entrypoint for moonshine-flow."""

from __future__ import annotations

import argparse
import datetime
import logging
import os
import platform
import sys
from importlib.metadata import PackageNotFoundError, version as package_version
from importlib.util import find_spec
from pathlib import Path

from moonshine_flow.app_bundle import (
    app_bundle_executable_path,
    default_app_bundle_path,
    get_app_bundle_codesign_info,
    install_app_bundle_from_env,
)
from moonshine_flow.config import default_config_path, load_config
from moonshine_flow.launchd import (
    LAUNCH_AGENT_LABEL,
    consume_restart_permission_suppression,
    install_launch_agent,
    launch_agent_log_paths,
    launch_agent_path,
    read_launch_agent_plist,
    resolve_launch_agent_program_prefix,
    restart_launch_agent,
    uninstall_launch_agent,
)
from moonshine_flow.logging_setup import configure_logging
from moonshine_flow.permissions import (
    PermissionReport,
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


def _format_command(command: list[str]) -> str:
    return " ".join(command)


def _format_launchd_permission_guidance(
    report: PermissionReport,
    *,
    target_executable: str | None,
) -> str:
    lines = [
        "Missing macOS permissions detected for launchd runtime:",
        *[f"- {item}" for item in report.missing],
        "",
        "Open: System Settings -> Privacy & Security",
        "Then enable this app in:",
        "- Accessibility",
        "- Input Monitoring",
        "- Microphone",
    ]
    if target_executable:
        lines.extend(
            [
                "",
                f"Launchd target executable: {target_executable}",
            ]
        )
    lines.extend(
        [
            "",
            "If the app does not appear in Input Monitoring, rerun "
            "`moonshine-flow install-launch-agent --request-permissions`.",
        ]
    )
    return "\n".join(lines)


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
    suppressed_after_restart = in_launchd_context and consume_restart_permission_suppression()
    if in_launchd_context and not report.all_granted:
        if suppressed_after_restart:
            LOGGER.info("Skipping permission request once after restart-launch-agent")
        else:
            # Trigger prompts from daemon context so launchd-triggered runs can obtain trust.
            if not report.accessibility:
                request_accessibility_permission()
            if not report.input_monitoring:
                request_input_monitoring_permission()
            if not report.microphone:
                request_microphone_permission()
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

    permission_check_command = [*resolve_launch_agent_program_prefix(), "check-permissions"]
    if args.request_permissions:
        permission_check_command.append("--request")
    print(f"Launchd permission check command: {_format_command(permission_check_command)}")

    probe = check_permissions_in_launchd_context(command=permission_check_command)
    if probe.report is None:
        print(
            "Could not verify launchd permission state before installing launch agent.",
            file=sys.stderr,
        )
        if probe.error:
            print(probe.error, file=sys.stderr)
        if probe.stdout:
            print(f"Launchd check stdout:\n{probe.stdout}", file=sys.stderr)
        if probe.stderr:
            print(f"Launchd check stderr:\n{probe.stderr}", file=sys.stderr)
        if not args.allow_missing_permissions:
            print(
                "\nLaunch agent installation was aborted because launchd permission state "
                "could not be verified.",
                file=sys.stderr,
            )
            print(
                "Retry after fixing permission checks, or run with "
                "`--allow-missing-permissions` to install anyway.",
                file=sys.stderr,
            )
            return 2

        print(
            "Warning: continuing with unverified permissions because "
            "`--allow-missing-permissions` was specified.",
            file=sys.stderr,
        )
    elif not probe.report.all_granted:
        guidance = _format_launchd_permission_guidance(
            probe.report,
            target_executable=permission_check_command[0] if permission_check_command else None,
        )
        if not args.allow_missing_permissions:
            print(guidance, file=sys.stderr)
            print(
                "\nLaunch agent installation was aborted because missing launchd permissions can "
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
    return 0


def cmd_uninstall_launch_agent(args: argparse.Namespace) -> int:
    del args
    removed = uninstall_launch_agent()
    if removed:
        print(f"Removed launch agent: {launch_agent_path()}")
    else:
        print("Launch agent is not installed.")
    return 0


def cmd_restart_launch_agent(args: argparse.Namespace) -> int:
    del args
    try:
        restarted = restart_launch_agent()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not restarted:
        print("Launch agent is not installed.")
        return 2
    print(f"Restarted launch agent: {launch_agent_path()}")
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


def _derive_launchd_permission_target(launchd_payload: dict[str, object] | None) -> str | None:
    """Resolve permission target path used by launchd daemon process."""
    if not isinstance(launchd_payload, dict):
        return None
    program_args = launchd_payload.get("ProgramArguments")
    if not isinstance(program_args, list) or not program_args:
        return None
    target = str(program_args[0]).strip()
    return target or None


def _latest_launchd_runtime_warning(err_log_path: Path) -> str | None:
    """Return latest launchd runtime warning text from daemon stderr log when present."""
    result = _latest_launchd_runtime_warning_with_timestamp(err_log_path)
    if result is None:
        return None
    return result[0]


def _latest_launchd_runtime_warning_with_timestamp(
    err_log_path: Path,
) -> tuple[str, str | None] | None:
    """Return (warning_message, detected_timestamp) from daemon stderr log, or None.

    *detected_timestamp* is the raw log line prefix of the first matching line,
    or None when no timestamp could be extracted.
    """
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

    def _extract_timestamp(line: str) -> str | None:
        """Return leading timestamp portion of a log line if recognisable."""
        # Common format: "2026-02-27 10:00:00,100 ..."
        parts = line.split(" ")
        if len(parts) >= 2 and len(parts[0]) == 10 and parts[0].count("-") == 2:
            return f"{parts[0]} {parts[1]}"
        return None

    for line in recent:
        if "This process is not trusted!" in line:
            return "pynput listener is not trusted in daemon runtime context", _extract_timestamp(
                line
            )
    for line in recent:
        if "Missing macOS permissions detected:" in line:
            return "daemon runtime detected missing macOS permissions", _extract_timestamp(line)
    return None


def _print_codesign_info(target_path: str) -> None:
    """Print codesign metadata for the app bundle derived from *target_path*."""
    # Determine the bundle path: if target is already an .app, use it directly;
    # otherwise try the default MoonshineFlow.app and resolve the executable mtime.
    candidate_bundle = default_app_bundle_path()
    exec_path = app_bundle_executable_path(candidate_bundle)

    if exec_path.exists():
        try:
            mtime = exec_path.stat().st_mtime
            mtime_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            print(f"App bundle executable mtime: {mtime_str} ({exec_path})")
        except OSError:
            pass

    codesign_info = get_app_bundle_codesign_info(candidate_bundle)
    if codesign_info:
        for key in ("CDHash", "Identifier", "TeamIdentifier", "Signature Type"):
            if key in codesign_info:
                print(f"App bundle {key}: {codesign_info[key]}")
    else:
        print(f"App bundle codesign info: unavailable ({candidate_bundle})")


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
        launchd_permission_target = None
    else:
        print(f"LaunchAgent plist: FOUND ({launch_agent_path()})")
        print(f"LaunchAgent label: {launchd_payload.get('Label', 'UNKNOWN')}")
        program_args = launchd_payload.get("ProgramArguments")
        if isinstance(program_args, list) and program_args:
            print(f"LaunchAgent program: {' '.join(str(part) for part in program_args)}")
        else:
            print("LaunchAgent program: UNKNOWN")
        launchd_permission_target = _derive_launchd_permission_target(launchd_payload)
        if launchd_permission_target:
            print(f"Launchd permission target (recommended): {launchd_permission_target}")
    print(f"Daemon stdout log: {out_log_path}")
    print(f"Daemon stderr log: {err_log_path}")
    runtime_warning_result = _latest_launchd_runtime_warning_with_timestamp(err_log_path)
    runtime_warning: str | None = None
    runtime_warning_timestamp: str | None = None
    if runtime_warning_result is not None:
        runtime_warning, runtime_warning_timestamp = runtime_warning_result
        timestamp_suffix = f" at {runtime_warning_timestamp}" if runtime_warning_timestamp else ""
        print(f"Launchd runtime status: WARNING ({runtime_warning}{timestamp_suffix})")

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
    print("Terminal permissions:", "OK" if report.all_granted else "INCOMPLETE")

    launchd_report = None
    probe_error = False
    should_check_launchd = bool(getattr(args, "launchd_check", False))
    if should_check_launchd:
        launchd_command = _derive_launchd_permission_check_command(launchd_payload)
        probe = check_permissions_in_launchd_context(command=launchd_command)
        if probe.command:
            print(f"Launchd check command: {_format_command(probe.command)}")
        else:
            print(f"Launchd check command: {_format_command(launchd_command)}")

        # Show app bundle codesign info alongside the launchd permission check
        if launchd_permission_target:
            _print_codesign_info(launchd_permission_target)

        if probe.report is not None:
            launchd_report = probe.report
            print("Launchd permissions:", "OK" if launchd_report.all_granted else "INCOMPLETE")
            if not launchd_report.all_granted:
                print(f"Launchd missing permissions: {', '.join(launchd_report.missing)}")
            if set(launchd_report.missing) != set(report.missing):
                print(
                    "Permission mismatch detected between terminal and launchd contexts. "
                    "Grant permissions for the launchd target shown above."
                )
            if runtime_warning:
                print(
                    "Launchd runtime log indicates trust failure despite check output. "
                    "Restart the launch agent after granting permissions."
                )
        else:
            probe_error = True
            print("Launchd permissions: ERROR")
            if probe.error:
                print(f"Launchd check error: {probe.error}")
            if probe.stdout:
                print(f"Launchd check stdout: {probe.stdout}")
            if probe.stderr:
                print(f"Launchd check stderr: {probe.stderr}")

    # Determine overall permissions status:
    # - INCOMPLETE: any definitive permission missing
    # - WARN: all checks pass but runtime log shows trust failure (TCC instability)
    # - OK: everything is granted and no runtime warning
    effective_incomplete = not report.all_granted
    if launchd_report is not None:
        effective_incomplete = effective_incomplete or not launchd_report.all_granted
    if probe_error:
        effective_incomplete = True

    # WARN = launchd check reports OK, but runtime log shows "not trusted"
    # This indicates TCC registered the permission but the signing identity may have drifted.
    effective_warn = (
        not effective_incomplete
        and runtime_warning is not None
        and launchd_report is not None
        and launchd_report.all_granted
    )
    # When launchd check was not run, runtime_warning alone causes INCOMPLETE (existing behaviour)
    if runtime_warning and not should_check_launchd:
        effective_incomplete = True

    if effective_incomplete:
        print("Permissions: INCOMPLETE")
    elif effective_warn:
        print("Permissions: WARN (launchd check OK but runtime not trusted)")
    else:
        print("Permissions: OK")

    if not report.all_granted:
        print(format_permission_guidance(report))
    elif launchd_report is not None and not launchd_report.all_granted:
        if launchd_permission_target:
            print(
                "Grant permissions for this launchd target and restart the launch agent: "
                f"{launchd_permission_target}"
            )
        else:
            print("Grant permissions for the launchd target shown above and restart the launch agent.")
    elif probe_error:
        print("Could not verify launchd permission state from launchctl output.")
    elif effective_warn:
        target = launchd_permission_target or str(recommended_permission_target())
        print(
            "Launchd check reports OK but runtime log shows trust failure. "
            "This typically means the app bundle was re-signed and TCC lost the binding. "
            "Re-grant Accessibility/Input Monitoring for this target and restart: "
            f"{target}"
        )
    elif runtime_warning:
        target = launchd_permission_target or str(recommended_permission_target())
        print(
            "Launchd runtime log indicates trust failure. "
            "Re-grant Accessibility/Input Monitoring for this target and restart: "
            f"{target}"
        )

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

    restart_parser = subparsers.add_parser("restart-launch-agent", help="Restart launchd agent")
    restart_parser.set_defaults(func=cmd_restart_launch_agent)

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
