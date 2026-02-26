"""Global hotkey listener."""

from __future__ import annotations

import logging
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
    ) -> None:
        self.key_name = key_name
        self._target_key = self._parse_key_name(key_name)
        self._on_press_callback = on_press
        self._on_release_callback = on_release
        self._pressed = False
        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)

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
        if not self._matches(key) or self._pressed:
            return
        self._pressed = True
        LOGGER.debug("Hotkey down: %s", self.key_name)
        self._on_press_callback()

    def _on_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if not self._matches(key) or not self._pressed:
            return
        self._pressed = False
        LOGGER.debug("Hotkey up: %s", self.key_name)
        self._on_release_callback()

    def start(self) -> None:
        """Start listening in background thread."""
        self._listener.start()

    def stop(self) -> None:
        """Stop listener."""
        self._listener.stop()

    def join(self) -> None:
        """Block until listener exits."""
        self._listener.join()
