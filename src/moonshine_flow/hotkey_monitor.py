"""Global hotkey listener."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from pynput import keyboard

LOGGER = logging.getLogger(__name__)


SPECIAL_KEYS: dict[str, keyboard.Key] = {
    "right_cmd": keyboard.Key.cmd_r,
    "left_cmd": keyboard.Key.cmd,
    "right_shift": keyboard.Key.shift_r,
    "left_shift": keyboard.Key.shift,
    "right_alt": keyboard.Key.alt_r,
    "left_alt": keyboard.Key.alt_l,
    "right_ctrl": keyboard.Key.ctrl_r,
    "left_ctrl": keyboard.Key.ctrl_l,
}


class HotkeyMonitor:
    """Monitor one key globally and emit press/release callbacks."""

    def __init__(
        self,
        key_name: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
        *,
        max_hold_seconds: float | None = None,
    ) -> None:
        self.key_name = key_name
        self._target_key = self._parse_key_name(key_name)
        self._on_press_callback = on_press
        self._on_release_callback = on_release
        self._max_hold_seconds = max_hold_seconds if (max_hold_seconds or 0) > 0 else None
        self._pressed = False
        self._lock = threading.Lock()
        self._release_timer: threading.Timer | None = None
        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)

    def _cancel_release_timer(self) -> None:
        if self._release_timer is None:
            return
        self._release_timer.cancel()
        self._release_timer = None

    def _schedule_release_timer(self) -> None:
        self._cancel_release_timer()
        if self._max_hold_seconds is None:
            return
        timer = threading.Timer(self._max_hold_seconds, self._force_release_if_stuck)
        timer.daemon = True
        self._release_timer = timer
        timer.start()

    @staticmethod
    def _parse_key_name(key_name: str) -> keyboard.Key | keyboard.KeyCode:
        name = key_name.strip().lower()
        if name in SPECIAL_KEYS:
            return SPECIAL_KEYS[name]

        if len(name) == 1:
            return keyboard.KeyCode.from_char(name)

        supported = ", ".join(sorted(SPECIAL_KEYS))
        raise ValueError(
            f"Unsupported key '{key_name}'. "
            f"Supported: {supported} or single characters"
        )

    def _matches(self, key: keyboard.Key | keyboard.KeyCode | None) -> bool:
        return key == self._target_key

    def _on_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        with self._lock:
            if not self._matches(key) or self._pressed:
                return
            self._pressed = True
            self._schedule_release_timer()
        LOGGER.debug("Hotkey down: %s", self.key_name)
        self._on_press_callback()

    def _on_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        with self._lock:
            if not self._matches(key) or not self._pressed:
                return
            self._pressed = False
            self._cancel_release_timer()
        LOGGER.debug("Hotkey up: %s", self.key_name)
        self._on_release_callback()

    def _force_release_if_stuck(self) -> None:
        with self._lock:
            if not self._pressed:
                return
            self._pressed = False
            self._release_timer = None
        LOGGER.warning(
            "Hotkey release fallback triggered after %.2fs: %s",
            self._max_hold_seconds or 0.0,
            self.key_name,
        )
        self._on_release_callback()

    def start(self) -> None:
        """Start listening in background thread."""
        self._listener.start()

    def stop(self) -> None:
        """Stop listener."""
        with self._lock:
            self._pressed = False
            self._cancel_release_timer()
        self._listener.stop()

    def join(self) -> None:
        """Block until listener exits."""
        self._listener.join()
