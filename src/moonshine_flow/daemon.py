"""Main daemon orchestration."""

from __future__ import annotations

import logging
import queue
import threading
import time

import numpy as np

from moonshine_flow.audio_recorder import AudioRecorder
from moonshine_flow.config import AppConfig
from moonshine_flow.hotkey_monitor import HotkeyMonitor
from moonshine_flow.output_injector import OutputInjector
from moonshine_flow.text_processing.interfaces import TextPostProcessor
from moonshine_flow.transcriber import MoonshineTranscriber

LOGGER = logging.getLogger(__name__)


class MoonshineFlowDaemon:
    """Hold-to-record, release-to-transcribe daemon."""

    def __init__(
        self,
        config: AppConfig,
        post_processor: TextPostProcessor | None = None,
    ) -> None:
        self.config = config
        self._stop_event = threading.Event()
        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue()

        self.recorder = AudioRecorder(
            sample_rate=config.audio.sample_rate,
            channels=config.audio.channels,
            dtype=config.audio.dtype,
            max_record_seconds=config.audio.max_record_seconds,
            input_device=config.audio.input_device,
            input_device_policy=config.audio.input_device_policy.value,
        )
        self.transcriber = MoonshineTranscriber(
            model_size=config.model.size.value,
            language=config.model.language,
            device=config.model.device,
            post_processor=post_processor,
        )
        self.injector = OutputInjector(
            mode=config.output.mode.value,
            paste_shortcut=config.output.paste_shortcut,
        )
        self.hotkey = HotkeyMonitor(
            key_name=config.hotkey.key,
            on_press=self._on_hotkey_down,
            on_release=self._on_hotkey_up,
            max_hold_seconds=float(config.audio.max_record_seconds) + 1.0,
        )

        self._worker = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="moonshine-worker",
        )

    def _on_hotkey_down(self) -> None:
        if self._stop_event.is_set():
            return
        if self.recorder.is_recording:
            return

        try:
            self.recorder.start()
            LOGGER.info("Recording started")
        except Exception:
            LOGGER.exception("Failed to start recording")

    def _on_hotkey_up(self) -> None:
        if self._stop_event.is_set() or not self.recorder.is_recording:
            return

        try:
            audio = self.recorder.stop()
        except Exception:
            LOGGER.exception("Failed to stop recording")
            return

        if audio.size == 0:
            LOGGER.info("Skipped empty audio capture")
            return

        self._audio_queue.put(audio)
        LOGGER.info("Queued audio for transcription")

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                audio = self._audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                text = self.transcriber.transcribe(audio, self.config.audio.sample_rate)
                if text:
                    self.injector.inject(text)
                else:
                    LOGGER.info("Transcription result was empty")
            except Exception:
                LOGGER.exception("Transcription pipeline failed")
            finally:
                self._audio_queue.task_done()

    def run_forever(self) -> None:
        """Run daemon until stop() is called."""
        LOGGER.info("Moonshine Flow daemon starting (%s)", self.transcriber.backend_summary())
        self._worker.start()
        self.hotkey.start()

        try:
            while not self._stop_event.is_set():
                time.sleep(0.2)
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop daemon components."""
        if self._stop_event.is_set():
            return

        self._stop_event.set()
        try:
            self.hotkey.stop()
        except Exception:
            LOGGER.debug("Failed to stop hotkey listener cleanly", exc_info=True)

        try:
            self.recorder.close()
        except Exception:
            LOGGER.debug("Failed to close recorder cleanly", exc_info=True)

        close = getattr(self.transcriber, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                LOGGER.debug("Failed to close transcriber cleanly", exc_info=True)

        LOGGER.info("Moonshine Flow daemon stopped")
