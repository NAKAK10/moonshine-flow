"""Microphone capture helpers."""

from __future__ import annotations

import logging
import threading
from typing import Any

import numpy as np
import sounddevice as sd

LOGGER = logging.getLogger(__name__)

_BLUETOOTH_INPUT_KEYWORDS = (
    "airpods",
    "bluetooth",
    "hands-free",
    "handsfree",
    "hfp",
    "headset",
)


class AudioRecorder:
    """Record short microphone audio into memory."""

    def __init__(
        self,
        sample_rate: int,
        channels: int,
        dtype: str,
        max_record_seconds: int,
        input_device: str | int | None = None,
        input_device_policy: str = "system_default",
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self.max_record_seconds = max_record_seconds
        self.input_device = input_device
        self.input_device_policy = input_device_policy

        self._lock = threading.Lock()
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._recording = False
        self._max_frames = self.sample_rate * self.max_record_seconds

    @staticmethod
    def _is_stream_active_state(stream: sd.InputStream | None) -> bool:
        if stream is None:
            return False

        try:
            closed = getattr(stream, "closed", False)
        except Exception:
            return False
        if isinstance(closed, bool) and closed:
            return False

        try:
            active = getattr(stream, "active", None)
        except Exception:
            return False
        if isinstance(active, bool):
            return active

        try:
            stopped = getattr(stream, "stopped", None)
        except Exception:
            return False
        if isinstance(stopped, bool):
            return not stopped

        # Fallback for stream doubles in tests that do not expose state.
        return True

    def _dispose_stream(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is None:
            return

        try:
            stream.stop()
        except Exception:
            LOGGER.debug("Stream was not active during stop", exc_info=True)
        finally:
            try:
                stream.close()
            except Exception:
                LOGGER.debug("Stream close failed", exc_info=True)

    @staticmethod
    def _is_input_device(device: Any) -> bool:
        return int(device.get("max_input_channels", 0)) > 0

    @staticmethod
    def _is_likely_bluetooth_input(device: Any) -> bool:
        name = str(device.get("name", "")).lower()
        return any(keyword in name for keyword in _BLUETOOTH_INPUT_KEYWORDS)

    def _resolve_input_device(self) -> str | int | None:
        if self.input_device is not None:
            return self.input_device

        if self.input_device_policy == "system_default":
            return None

        try:
            devices = sd.query_devices()
            default_input_index = int(sd.default.device[0])
        except Exception:
            LOGGER.debug("Failed to query audio devices; using system default input", exc_info=True)
            return None

        if self.input_device_policy == "external_preferred":
            for index, device in enumerate(devices):
                if not self._is_input_device(device):
                    continue
                if index == default_input_index:
                    continue
                return index
            return None

        if self.input_device_policy == "playback_friendly":
            default_input = None
            if 0 <= default_input_index < len(devices):
                default_input = devices[default_input_index]

            if default_input is not None and not self._is_likely_bluetooth_input(default_input):
                return None

            for index, device in enumerate(devices):
                if not self._is_input_device(device):
                    continue
                if self._is_likely_bluetooth_input(device):
                    continue
                return index

            LOGGER.warning(
                "Playback-friendly input policy could not find a non-Bluetooth mic; "
                "using system default"
            )
            return None

        LOGGER.warning(
            "Unknown input_device_policy=%s; using system default",
            self.input_device_policy,
        )
        return None

    def _ensure_stream(self) -> None:
        if self._is_stream_active_state(self._stream):
            return
        if self._stream is not None:
            LOGGER.warning("Detected stale audio input stream; reopening input stream")
            self._dispose_stream()

        stream_kwargs: dict[str, Any] = {
            "samplerate": self.sample_rate,
            "channels": self.channels,
            "dtype": self.dtype,
            "callback": self._callback,
        }
        resolved_input_device = self._resolve_input_device()
        if resolved_input_device is not None:
            stream_kwargs["device"] = resolved_input_device
            LOGGER.info("Using input device: %s", resolved_input_device)
        else:
            LOGGER.info("Using system default input device")

        self._stream = sd.InputStream(**stream_kwargs)
        self._stream.start()

    @property
    def is_recording(self) -> bool:
        return self._recording

    def is_stream_active(self) -> bool:
        with self._lock:
            stream = self._stream
        return self._is_stream_active_state(stream)

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: Any,
        status: sd.CallbackFlags,
    ) -> None:
        del time_info
        if status:
            LOGGER.warning("Audio input status: %s", status)

        with self._lock:
            if not self._recording:
                return
            self._frames.append(indata.copy())
            total = sum(chunk.shape[0] for chunk in self._frames)
            if total >= self._max_frames:
                LOGGER.warning("Reached max recording duration (%ss)", self.max_record_seconds)
                self._recording = False
                raise sd.CallbackStop

    def start(self) -> None:
        """Start recording audio into memory."""
        with self._lock:
            if self._recording:
                return
            self._frames = []
            self._recording = True

        try:
            self._ensure_stream()
            LOGGER.debug("Audio recording started")
        except Exception:
            with self._lock:
                self._recording = False
            self.close()
            raise

    def stop(self) -> np.ndarray:
        """Stop recording and return audio samples."""
        self._dispose_stream()

        with self._lock:
            self._recording = False
            if not self._frames:
                return np.empty((0, self.channels), dtype=self.dtype)
            merged = np.concatenate(self._frames, axis=0)
            self._frames = []

        LOGGER.debug("Audio recording stopped: %d samples", merged.shape[0])
        return merged

    def close(self) -> None:
        """Close active input stream and reset state."""
        with self._lock:
            self._recording = False
            self._frames = []

        if self._stream is None:
            return
        self._dispose_stream()
