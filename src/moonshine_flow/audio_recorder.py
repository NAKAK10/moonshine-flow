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
        input_device: str | int | None = None,
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

    def _ensure_stream(self) -> None:
        if self._stream is not None:
            return

        stream_kwargs: dict[str, Any] = {
            "samplerate": self.sample_rate,
            "channels": self.channels,
            "dtype": self.dtype,
            "callback": self._callback,
        }
        if self.input_device is not None:
            stream_kwargs["device"] = self.input_device

        self._stream = sd.InputStream(**stream_kwargs)
        self._stream.start()

    @property
    def is_recording(self) -> bool:
        return self._recording

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
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                LOGGER.debug("Stream was not active during stop", exc_info=True)
            finally:
                self._stream.close()
                self._stream = None

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

        try:
            self._stream.stop()
        except Exception:
            LOGGER.debug("Stream was not active during close", exc_info=True)
        finally:
            try:
                self._stream.close()
            finally:
                self._stream = None
