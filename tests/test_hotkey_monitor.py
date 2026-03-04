from __future__ import annotations

from ptarmigan_flow.hotkey_monitor import HotkeyMonitor


class _FakeListener:
    def __init__(self, on_press, on_release):
        self.on_press = on_press
        self.on_release = on_release

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def join(self) -> None:
        return None


def test_force_release_recovers_stuck_pressed_state(monkeypatch) -> None:
    monkeypatch.setattr("ptarmigan_flow.hotkey_monitor.keyboard.Listener", _FakeListener)

    pressed = 0
    released = 0

    def on_press() -> None:
        nonlocal pressed
        pressed += 1

    def on_release() -> None:
        nonlocal released
        released += 1

    monitor = HotkeyMonitor("a", on_press=on_press, on_release=on_release, max_hold_seconds=1.0)

    monitor._on_press(monitor._target_key)
    monitor._force_release_if_stuck()
    monitor._on_release(monitor._target_key)

    assert pressed == 1
    assert released == 1


def test_stop_clears_pressed_state(monkeypatch) -> None:
    monkeypatch.setattr("ptarmigan_flow.hotkey_monitor.keyboard.Listener", _FakeListener)

    pressed = 0

    def on_press() -> None:
        nonlocal pressed
        pressed += 1

    monitor = HotkeyMonitor("a", on_press=on_press, on_release=lambda: None, max_hold_seconds=1.0)

    monitor._on_press(monitor._target_key)
    monitor.stop()
    monitor._on_press(monitor._target_key)

    assert pressed == 2


def test_duplicate_press_recovers_missed_release(monkeypatch) -> None:
    monkeypatch.setattr("ptarmigan_flow.hotkey_monitor.keyboard.Listener", _FakeListener)

    pressed = 0
    released = 0

    def on_press() -> None:
        nonlocal pressed
        pressed += 1

    def on_release() -> None:
        nonlocal released
        released += 1

    monitor = HotkeyMonitor("a", on_press=on_press, on_release=on_release, max_hold_seconds=1.0)

    monitor._on_press(monitor._target_key)
    monitor._on_press(monitor._target_key)

    assert pressed == 2
    assert released == 1


def test_is_pressed_reflects_hotkey_state(monkeypatch) -> None:
    monkeypatch.setattr("ptarmigan_flow.hotkey_monitor.keyboard.Listener", _FakeListener)

    monitor = HotkeyMonitor("a", on_press=lambda: None, on_release=lambda: None, max_hold_seconds=1.0)
    assert monitor.is_pressed() is False

    monitor._on_press(monitor._target_key)
    assert monitor.is_pressed() is True

    monitor._on_release(monitor._target_key)
    assert monitor.is_pressed() is False


def test_is_pressed_prefers_physical_state_when_available(monkeypatch) -> None:
    monkeypatch.setattr("ptarmigan_flow.hotkey_monitor.keyboard.Listener", _FakeListener)

    monitor = HotkeyMonitor("a", on_press=lambda: None, on_release=lambda: None, max_hold_seconds=1.0)
    monitor._on_press(monitor._target_key)
    monitor._physical_pressed_state = lambda: True
    assert monitor.is_pressed() is True

    monitor._physical_pressed_state = lambda: False
    assert monitor.is_pressed() is True


def test_is_pressed_ignores_physical_false(monkeypatch) -> None:
    monkeypatch.setattr("ptarmigan_flow.hotkey_monitor.keyboard.Listener", _FakeListener)

    monitor = HotkeyMonitor("a", on_press=lambda: None, on_release=lambda: None, max_hold_seconds=1.0)
    monitor._physical_pressed_state = lambda: False
    monitor._on_press(monitor._target_key)

    assert monitor.is_pressed() is True


def test_on_press_accepts_event_even_when_physical_released(monkeypatch) -> None:
    monkeypatch.setattr("ptarmigan_flow.hotkey_monitor.keyboard.Listener", _FakeListener)

    pressed = 0

    def on_press() -> None:
        nonlocal pressed
        pressed += 1

    monitor = HotkeyMonitor("a", on_press=on_press, on_release=lambda: None, max_hold_seconds=1.0)
    monitor._physical_pressed_state = lambda: False

    monitor._on_press(monitor._target_key)

    assert pressed == 1
    assert monitor.is_pressed() is True
