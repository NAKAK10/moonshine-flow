"""Lifecycle manager for local vLLM server processes."""

from __future__ import annotations

import logging
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import urlopen

LOGGER = logging.getLogger(__name__)


def _find_open_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass(slots=True)
class VLLMServerConfig:
    host: str = "127.0.0.1"
    startup_timeout_seconds: float = 120.0
    health_poll_interval_seconds: float = 0.5
    log_tail_lines: int = 80


class VLLMServerManager:
    """Start/stop a local vLLM server for one configured model."""

    def __init__(self, config: VLLMServerConfig | None = None) -> None:
        self._config = config or VLLMServerConfig()
        self._process: subprocess.Popen[str] | None = None
        self._model_id: str | None = None
        self._port: int | None = None
        self._last_activity_at_monotonic: float | None = None
        self._lock = threading.Lock()

    @property
    def endpoint_url(self) -> str:
        with self._lock:
            return self._endpoint_url_locked()

    @property
    def websocket_url(self) -> str:
        endpoint = self.endpoint_url
        return endpoint.replace("http://", "ws://", 1) + "/v1/realtime?intent=transcription"

    def ensure_started(self, model_id: str) -> str:
        with self._lock:
            if self._process is not None and self._process.poll() is None and self._model_id == model_id:
                self._last_activity_at_monotonic = time.monotonic()
                return self._endpoint_url_locked()
        self.stop()
        self._start(model_id)
        with self._lock:
            self._last_activity_at_monotonic = time.monotonic()
            return self._endpoint_url_locked()

    def mark_activity(self) -> None:
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                return
            self._last_activity_at_monotonic = time.monotonic()

    def stop_if_idle(self, idle_seconds: float) -> bool:
        if idle_seconds <= 0.0:
            return False

        process_to_stop: subprocess.Popen[str] | None = None
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None:
                return False
            now = time.monotonic()
            last_activity = self._last_activity_at_monotonic
            if last_activity is None:
                self._last_activity_at_monotonic = now
                return False
            idle_for = now - last_activity
            if idle_for < idle_seconds:
                return False

            LOGGER.info(
                "💨 Stopped idle local vLLM server after %.1fs inactivity",
                idle_for,
            )
            process_to_stop = process
            self._clear_state_locked()

        if process_to_stop is None:
            return False
        self._terminate_process(process_to_stop)
        return True

    def _start(self, model_id: str) -> None:
        port = _find_open_port()
        command = self._build_command(model_id=model_id, port=port)
        LOGGER.info("🚀 Starting local vLLM server: %s", " ".join(command))
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        with self._lock:
            self._process = process
            self._model_id = model_id
            self._port = port
            self._last_activity_at_monotonic = time.monotonic()
        try:
            self._wait_until_ready(process)
        except Exception:
            self.stop()
            raise

    @staticmethod
    def _build_command(*, model_id: str, port: int) -> list[str]:
        vllm_bin = shutil.which("vllm")
        if vllm_bin:
            return [
                vllm_bin,
                "serve",
                model_id,
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ]
        return [
            sys.executable,
            "-m",
            "vllm.entrypoints.openai.api_server",
            "--model",
            model_id,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ]

    def _wait_until_ready(self, process: subprocess.Popen[str]) -> None:
        deadline = time.monotonic() + self._config.startup_timeout_seconds
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(self._startup_failure_message(process))
            if self._is_healthy():
                return
            time.sleep(self._config.health_poll_interval_seconds)
        raise RuntimeError("Timed out waiting for local vLLM server to become ready")

    def _is_healthy(self) -> bool:
        try:
            endpoint = self.endpoint_url
        except RuntimeError:
            return False
        for path in ("/health", "/v1/models"):
            try:
                with urlopen(endpoint + path, timeout=1.0):
                    return True
            except URLError:
                continue
            except TimeoutError:
                continue
            except Exception:
                continue
        return False

    def _startup_failure_message(self, process: subprocess.Popen[str] | None) -> str:
        if process is None:
            return "vLLM server failed to start"
        stdout = ""
        stderr = ""
        try:
            if process.stdout is not None:
                stdout = self._tail_stream(process.stdout)
            if process.stderr is not None:
                stderr = self._tail_stream(process.stderr)
        except Exception:
            pass
        detail_parts = ["Local vLLM server exited before startup completed"]
        if stdout:
            detail_parts.append(f"stdout tail:\n{stdout}")
        if stderr:
            detail_parts.append(f"stderr tail:\n{stderr}")
        return "\n".join(detail_parts)

    def _tail_stream(self, stream) -> str:
        tail: deque[str] = deque(maxlen=self._config.log_tail_lines)
        for line in stream:
            tail.append(line.rstrip("\n"))
        return "\n".join(tail)

    def stop(self) -> None:
        with self._lock:
            process = self._process
            self._clear_state_locked()
        if process is None:
            return
        if process.poll() is None:
            LOGGER.info("💨 Stopping local vLLM server")
        self._terminate_process(process)

    def _endpoint_url_locked(self) -> str:
        if self._port is None:
            raise RuntimeError("vLLM server is not started")
        return f"http://{self._config.host}:{self._port}"

    def _clear_state_locked(self) -> None:
        self._process = None
        self._model_id = None
        self._port = None
        self._last_activity_at_monotonic = None

    @staticmethod
    def _terminate_process(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3.0)
