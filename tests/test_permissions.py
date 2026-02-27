import sys
from pathlib import Path
from types import SimpleNamespace

from moonshine_flow.permissions import (
    PermissionReport,
    check_accessibility_permission,
    format_permission_guidance,
    recommended_permission_target,
    request_accessibility_permission,
    request_all_permissions,
)


def test_request_all_permissions_noop_when_already_granted(monkeypatch) -> None:
    granted = PermissionReport(microphone=True, accessibility=True, input_monitoring=True)
    monkeypatch.setattr("moonshine_flow.permissions.check_all_permissions", lambda: granted)

    result = request_all_permissions()
    assert result.all_granted


def test_request_all_permissions_requests_only_missing(monkeypatch) -> None:
    states = [
        PermissionReport(microphone=False, accessibility=True, input_monitoring=False),
        PermissionReport(microphone=True, accessibility=True, input_monitoring=True),
    ]
    calls = {"mic": 0, "ax": 0, "im": 0}

    def fake_check_all_permissions() -> PermissionReport:
        return states.pop(0)

    def fake_request_mic() -> bool:
        calls["mic"] += 1
        return True

    def fake_request_ax() -> bool:
        calls["ax"] += 1
        return True

    def fake_request_im() -> bool:
        calls["im"] += 1
        return True

    monkeypatch.setattr(
        "moonshine_flow.permissions.check_all_permissions",
        fake_check_all_permissions,
    )
    monkeypatch.setattr(
        "moonshine_flow.permissions.request_microphone_permission",
        fake_request_mic,
    )
    monkeypatch.setattr(
        "moonshine_flow.permissions.request_accessibility_permission",
        fake_request_ax,
    )
    monkeypatch.setattr(
        "moonshine_flow.permissions.request_input_monitoring_permission",
        fake_request_im,
    )

    result = request_all_permissions()

    assert result.all_granted
    assert calls == {"mic": 1, "ax": 0, "im": 1}


def test_check_accessibility_permission_uses_application_services(monkeypatch) -> None:
    monkeypatch.setattr("moonshine_flow.permissions._is_macos", lambda: True)
    monkeypatch.setitem(
        sys.modules,
        "ApplicationServices",
        SimpleNamespace(AXIsProcessTrusted=lambda: True),
    )

    assert check_accessibility_permission()


def test_request_accessibility_permission_prompts_via_application_services(monkeypatch) -> None:
    monkeypatch.setattr("moonshine_flow.permissions._is_macos", lambda: True)
    calls = {"count": 0}

    def fake_trusted() -> bool:
        return calls["count"] > 0

    def fake_prompt(_options: dict[object, object]) -> bool:
        calls["count"] += 1
        return True

    monkeypatch.setitem(
        sys.modules,
        "ApplicationServices",
        SimpleNamespace(
            AXIsProcessTrusted=fake_trusted,
            AXIsProcessTrustedWithOptions=fake_prompt,
            kAXTrustedCheckOptionPrompt=object(),
        ),
    )

    assert request_accessibility_permission()
    assert calls["count"] == 1


def test_format_permission_guidance_includes_current_executable(monkeypatch) -> None:
    monkeypatch.setattr(sys, "executable", "/tmp/python3.11")
    report = PermissionReport(microphone=False, accessibility=True, input_monitoring=False)

    guidance = format_permission_guidance(report)

    assert "Missing macOS permissions detected:" in guidance
    assert "Current executable:" in guidance
    assert "Preferred permission target:" in guidance
    assert guidance.count("python3.11") >= 1


def test_format_permission_guidance_includes_preferred_target_and_launchd_hint(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "executable",
        "/opt/homebrew/Cellar/python@3.11/3.11.14_3/Frameworks/Python.framework/Versions/3.11/bin/python3.11",
    )
    monkeypatch.setenv("XPC_SERVICE_NAME", "com.moonshineflow.daemon")
    report = PermissionReport(microphone=False, accessibility=False, input_monitoring=False)

    guidance = format_permission_guidance(report)

    assert "Preferred permission target:" in guidance
    assert (
        "/opt/homebrew/opt/python@3.11/Frameworks/Python.framework/Versions/3.11/Resources/Python.app"
        in guidance
    )
    assert "enable the preferred target above" in guidance
    assert "Detected launchd context: com.moonshineflow.daemon" in guidance


def test_recommended_permission_target_falls_back_to_executable(monkeypatch) -> None:
    monkeypatch.setattr(sys, "executable", "/tmp/custom/bin/python")

    resolved = recommended_permission_target()
    assert str(resolved).endswith("/tmp/custom/bin/python")
