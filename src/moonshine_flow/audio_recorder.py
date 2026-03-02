"""Microphone capture helpers."""

from __future__ import annotations

import logging
import threading
from typing import Any

import numpy as np
import sounddevice as sd

LOGGER = logging.getLogger(__name__)


class AudioRecorder:
    """Record short microphone audio into memory."""

    def __init__(
        self,
        sample_rate: int,
        channels: int,
        dtype: str,
        max_record_seconds: int,
        input_device: int | str | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self.max_record_seconds = max_record_seconds
        self.input_device = input_device

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

    def _resolve_input_device(self) -> int | str | None:
        return self.input_device

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
