"""Text output injection into focused macOS app."""

from __future__ import annotations

import logging
import shlex
import subprocess

import pyperclip

LOGGER = logging.getLogger(__name__)


APPLE_MODIFIERS = {
    "cmd": "command down",
    "command": "command down",
    "ctrl": "control down",
    "control": "control down",
    "alt": "option down",
    "option": "option down",
    "shift": "shift down",
}


class OutputInjector:
    """Inject transcription text into currently focused app."""

    def __init__(self, mode: str, paste_shortcut: str) -> None:
        self.mode = mode
        self.paste_shortcut = paste_shortcut

    @staticmethod
    def _parse_shortcut(shortcut: str) -> tuple[str, list[str]]:
        parts = [token.strip().lower() for token in shortcut.split("+") if token.strip()]
        if not parts:
            raise ValueError("Shortcut cannot be empty")

        key = parts[-1]
        modifiers: list[str] = []
        for token in parts[:-1]:
            if token not in APPLE_MODIFIERS:
                raise ValueError(f"Unsupported shortcut modifier: {token}")
            modifiers.append(APPLE_MODIFIERS[token])

        if len(key) != 1:
            raise ValueError("Paste shortcut key must be a single character")
        return key, modifiers

    def _send_shortcut(self) -> None:
        key, modifiers = self._parse_shortcut(self.paste_shortcut)
        modifiers_script = ", ".join(modifiers)

        if modifiers_script:
            script = (
                f'tell application "System Events" '
                f'to keystroke "{key}" using {{{modifiers_script}}}'
            )
        else:
            script = f'tell application "System Events" to keystroke "{key}"'

        LOGGER.debug("Executing AppleScript: %s", shlex.quote(script))
        subprocess.run(["osascript", "-e", script], check=True)

    def inject(self, text: str) -> bool:
        """Copy text to clipboard and paste into active app."""
        if not text.strip():
            LOGGER.debug("Skipping empty transcription output")
            return False

        if self.mode != "clipboard_paste":
            raise ValueError(f"Unsupported output mode: {self.mode}")

        pyperclip.copy(text)
        self._send_shortcut()
        LOGGER.info("Transcription pasted into active app")
        return True
