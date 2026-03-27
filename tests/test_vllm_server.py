from __future__ import annotations

import logging

import pytest

import ptarmigan_flow.stt.server as server_module


class _FakeProcess:
    def __init__(self, *, running: bool = True) -> None:
        self._running = running
        self.terminate_calls = 0
        self.wait_calls = 0
        self.kill_calls = 0

    def poll(self) -> int | None:
        return None if self._running else 0

    def terminate(self) -> None:
        self.terminate_calls += 1
        self._running = False

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        self.wait_calls += 1
        return 0

    def kill(self) -> None:
        self.kill_calls += 1
        self._running = False


def _attach_running_process(
    manager: server_module.VLLMServerManager,
    *,
    process: _FakeProcess,
    model_id: str = "model",
    port: int = 8000,
    last_activity: float | None = None,
) -> None:
    with manager._lock:
        manager._process = process
        manager._model_id = model_id
        manager._port = port
        manager._last_activity_at_monotonic = last_activity


def test_stop_if_idle_skips_when_disabled() -> None:
    manager = server_module.VLLMServerManager()
    process = _FakeProcess()
    _attach_running_process(manager, process=process, last_activity=10.0)

    stopped = manager.stop_if_idle(0.0)

    assert stopped is False
    assert process.terminate_calls == 0


def test_stop_if_idle_waits_until_threshold(monkeypatch) -> None:
    manager = server_module.VLLMServerManager()
    process = _FakeProcess()
    _attach_running_process(manager, process=process, last_activity=50.0)
    monkeypatch.setattr(server_module.time, "monotonic", lambda: 70.0)

    stopped = manager.stop_if_idle(30.0)

    assert stopped is False
    assert process.terminate_calls == 0


def test_stop_if_idle_stops_after_threshold(monkeypatch) -> None:
    manager = server_module.VLLMServerManager()
    process = _FakeProcess()
    _attach_running_process(manager, process=process, last_activity=10.0)
    monkeypatch.setattr(server_module.time, "monotonic", lambda: 50.0)

    stopped = manager.stop_if_idle(30.0)

    assert stopped is True
    assert process.terminate_calls == 1
    assert process.wait_calls == 1
    assert process.kill_calls == 0
    with manager._lock:
        assert manager._process is None
        assert manager._model_id is None
        assert manager._port is None
        assert manager._last_activity_at_monotonic is None


def test_stop_if_idle_logs_wind_icon(monkeypatch, caplog) -> None:
    manager = server_module.VLLMServerManager()
    process = _FakeProcess()
    _attach_running_process(manager, process=process, last_activity=10.0)
    monkeypatch.setattr(server_module.time, "monotonic", lambda: 50.0)

    with caplog.at_level(logging.INFO, logger=server_module.__name__):
        stopped = manager.stop_if_idle(30.0)

    assert stopped is True
    assert any("💨 Stopped idle local vLLM server" in entry.message for entry in caplog.records)


def test_stop_if_idle_sets_activity_when_unknown(monkeypatch) -> None:
    manager = server_module.VLLMServerManager()
    process = _FakeProcess()
    _attach_running_process(manager, process=process, last_activity=None)
    monkeypatch.setattr(server_module.time, "monotonic", lambda: 123.0)

    stopped = manager.stop_if_idle(30.0)

    assert stopped is False
    assert process.terminate_calls == 0
    with manager._lock:
        assert manager._last_activity_at_monotonic == 123.0


def test_ensure_started_reuses_process_for_same_model(monkeypatch) -> None:
    manager = server_module.VLLMServerManager()
    process = _FakeProcess()
    _attach_running_process(manager, process=process, model_id="same-model", port=7777, last_activity=1.0)
    monkeypatch.setattr(server_module.time, "monotonic", lambda: 42.0)

    endpoint = manager.ensure_started("same-model")

    assert endpoint == "http://127.0.0.1:7777"
    assert process.terminate_calls == 0
    with manager._lock:
        assert manager._last_activity_at_monotonic == 42.0


def test_stop_logs_wind_icon_for_running_process(caplog) -> None:
    manager = server_module.VLLMServerManager()
    process = _FakeProcess()
    _attach_running_process(manager, process=process, last_activity=10.0)

    with caplog.at_level(logging.INFO, logger=server_module.__name__):
        manager.stop()

    assert any("💨 Stopping local vLLM server" in entry.message for entry in caplog.records)


def test_start_logs_rocket_icon(monkeypatch, caplog) -> None:
    manager = server_module.VLLMServerManager()
    started_process = _FakeProcess()

    monkeypatch.setattr(server_module, "_find_open_port", lambda: 9911)
    monkeypatch.setattr(manager, "_wait_until_ready", lambda _process: None)
    monkeypatch.setattr(server_module.subprocess, "Popen", lambda *_args, **_kwargs: started_process)

    with caplog.at_level(logging.INFO, logger=server_module.__name__):
        manager._start("mistralai/Voxtral-Mini-4B-Realtime-2602")

    assert any("🚀 Starting local vLLM server" in entry.message for entry in caplog.records)


@pytest.mark.parametrize(
    ("startup_preset", "max_model_len", "expected_suffix"),
    [
        ("off", 2048, ["--max-model-len", "2048"]),
        ("balanced", 4096, ["--max-model-len", "4096", "-O1"]),
        ("fastest", 8192, ["--max-model-len", "8192", "-O0", "--enforce-eager"]),
    ],
)
def test_build_command_uses_vllm_binary_when_available(
    monkeypatch,
    startup_preset: str,
    max_model_len: int,
    expected_suffix: list[str],
) -> None:
    monkeypatch.setattr(server_module.shutil, "which", lambda _name: "/tmp/vllm")

    command = server_module.VLLMServerManager._build_command(
        model_id="mistralai/Voxtral-Mini-4B-Realtime-2602",
        port=8000,
        startup_preset=startup_preset,
        max_model_len=max_model_len,
    )

    assert command == [
        "/tmp/vllm",
        "serve",
        "mistralai/Voxtral-Mini-4B-Realtime-2602",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        *expected_suffix,
    ]


@pytest.mark.parametrize(
    ("startup_preset", "max_model_len", "expected_suffix"),
    [
        ("off", 2048, ["--max-model-len", "2048"]),
        ("balanced", 4096, ["--max-model-len", "4096", "-O1"]),
        ("fastest", 8192, ["--max-model-len", "8192", "-O0", "--enforce-eager"]),
    ],
)
def test_build_command_falls_back_to_python_module_when_vllm_binary_missing(
    monkeypatch,
    startup_preset: str,
    max_model_len: int,
    expected_suffix: list[str],
) -> None:
    monkeypatch.setattr(server_module.shutil, "which", lambda _name: None)
    monkeypatch.setattr(server_module.sys, "executable", "/tmp/python")

    command = server_module.VLLMServerManager._build_command(
        model_id="mistralai/Voxtral-Mini-4B-Realtime-2602",
        port=8000,
        startup_preset=startup_preset,
        max_model_len=max_model_len,
    )

    assert command == [
        "/tmp/python",
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--model",
        "mistralai/Voxtral-Mini-4B-Realtime-2602",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        *expected_suffix,
    ]


def test_build_command_rejects_unknown_startup_preset(monkeypatch) -> None:
    monkeypatch.setattr(server_module.shutil, "which", lambda _name: "/tmp/vllm")

    with pytest.raises(ValueError, match="Unsupported vLLM startup preset"):
        server_module.VLLMServerManager._build_command(
            model_id="mistralai/Voxtral-Mini-4B-Realtime-2602",
            port=8000,
            startup_preset="unknown",
            max_model_len=2048,
        )
