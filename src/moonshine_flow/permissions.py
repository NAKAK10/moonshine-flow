"""macOS permission detection utilities."""

from __future__ import annotations

import logging
import platform
from dataclasses import dataclass
from threading import Event

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class PermissionReport:
    """Permission states used by CLI and daemon startup."""

    microphone: bool
    accessibility: bool
    input_monitoring: bool

    @property
    def all_granted(self) -> bool:
        return self.microphone and self.accessibility and self.input_monitoring

    @property
    def missing(self) -> list[str]:
        missing_permissions: list[str] = []
        if not self.microphone:
            missing_permissions.append("Microphone")
        if not self.accessibility:
            missing_permissions.append("Accessibility")
        if not self.input_monitoring:
            missing_permissions.append("Input Monitoring")
        return missing_permissions


def _is_macos() -> bool:
    return platform.system() == "Darwin"


def check_microphone_permission() -> bool:
    """Best-effort microphone permission preflight."""
    if not _is_macos():
        return True

    try:
        from AVFoundation import AVAuthorizationStatusAuthorized, AVCaptureDevice, AVMediaTypeAudio

        status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio)
        return status == AVAuthorizationStatusAuthorized
    except Exception as exc:
        LOGGER.debug("Could not preflight microphone permission via AVFoundation: %s", exc)

    try:
        import sounddevice as sd

        with sd.InputStream(channels=1, samplerate=16000, blocksize=64):
            pass
        return True
    except Exception as exc:
        LOGGER.debug("Could not probe microphone stream: %s", exc)
        return False


def check_accessibility_permission() -> bool:
    """Check macOS Accessibility permission."""
    if not _is_macos():
        return True

    try:
        import ApplicationServices as app_services

        return bool(app_services.AXIsProcessTrusted())
    except Exception as exc:
        LOGGER.debug(
            "Could not preflight accessibility permission via ApplicationServices: %s",
            exc,
        )

    try:
        import Quartz

        trusted = getattr(Quartz, "AXIsProcessTrusted", None)
        if trusted is None:
            return False
        return bool(trusted())
    except Exception as exc:
        LOGGER.debug("Could not preflight accessibility permission via Quartz: %s", exc)
        return False


def check_input_monitoring_permission() -> bool:
    """Check macOS Input Monitoring permission."""
    if not _is_macos():
        return True

    try:
        import Quartz

        preflight = getattr(Quartz, "CGPreflightListenEventAccess", None)
        if preflight is None:
            return True
        return bool(preflight())
    except Exception as exc:
        LOGGER.debug("Could not preflight input monitoring permission: %s", exc)
        return False


def check_all_permissions() -> PermissionReport:
    """Run all permission probes."""
    return PermissionReport(
        microphone=check_microphone_permission(),
        accessibility=check_accessibility_permission(),
        input_monitoring=check_input_monitoring_permission(),
    )


def request_microphone_permission(timeout_seconds: float = 10.0) -> bool:
    """Trigger microphone permission request if possible."""
    if not _is_macos():
        return True

    if check_microphone_permission():
        return True

    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeAudio

        done = Event()

        def completion(_granted: bool) -> None:
            done.set()

        AVCaptureDevice.requestAccessForMediaType_completionHandler_(
            AVMediaTypeAudio,
            completion,
        )
        done.wait(timeout_seconds)
    except Exception as exc:
        LOGGER.debug("Could not request microphone permission: %s", exc)

    return check_microphone_permission()


def request_accessibility_permission() -> bool:
    """Trigger Accessibility prompt if possible."""
    if not _is_macos():
        return True

    if check_accessibility_permission():
        return True

    try:
        import ApplicationServices as app_services

        options = {app_services.kAXTrustedCheckOptionPrompt: True}
        app_services.AXIsProcessTrustedWithOptions(options)
    except Exception as exc:
        LOGGER.debug(
            "Could not request accessibility permission via ApplicationServices: %s",
            exc,
        )
        try:
            import Quartz

            trusted_with_options = getattr(Quartz, "AXIsProcessTrustedWithOptions", None)
            prompt_key = getattr(Quartz, "kAXTrustedCheckOptionPrompt", None)
            if trusted_with_options is not None and prompt_key is not None:
                trusted_with_options({prompt_key: True})
        except Exception as fallback_exc:
            LOGGER.debug(
                "Could not request accessibility permission via Quartz: %s",
                fallback_exc,
            )

    return check_accessibility_permission()


def request_input_monitoring_permission() -> bool:
    """Trigger Input Monitoring prompt if possible."""
    if not _is_macos():
        return True

    if check_input_monitoring_permission():
        return True

    try:
        import Quartz

        request = getattr(Quartz, "CGRequestListenEventAccess", None)
        if request is not None:
            request()
    except Exception as exc:
        LOGGER.debug("Could not request input monitoring permission: %s", exc)

    return check_input_monitoring_permission()


def request_all_permissions() -> PermissionReport:
    """Request any missing permissions and return the final state."""
    before = check_all_permissions()
    if before.all_granted:
        return before

    if not before.microphone:
        request_microphone_permission()
    if not before.accessibility:
        request_accessibility_permission()
    if not before.input_monitoring:
        request_input_monitoring_permission()

    return check_all_permissions()


def format_permission_guidance(report: PermissionReport) -> str:
    """Build user-facing setup instructions for missing permissions."""
    if report.all_granted:
        return "All required permissions are granted."

    lines = [
        "Missing macOS permissions detected:",
        *[f"- {item}" for item in report.missing],
        "",
        "Open: System Settings -> Privacy & Security",
        "Then enable this terminal/app in:",
        "- Microphone",
        "- Accessibility",
        "- Input Monitoring",
        "",
        "After changing permissions, restart moonshine-flow.",
    ]
    return "\n".join(lines)
