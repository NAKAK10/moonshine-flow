import sys
from types import SimpleNamespace

from moonshine_flow.permissions import (
    PermissionReport,
    check_accessibility_permission,
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
