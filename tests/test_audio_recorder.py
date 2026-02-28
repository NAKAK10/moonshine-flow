from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

import moonshine_flow.audio_recorder as audio_recorder_module
from moonshine_flow.audio_recorder import AudioRecorder


class _FakeStream:
    created = 0
    started = 0
    stopped = 0
    closed = 0
    last_kwargs = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        _FakeStream.last_kwargs = kwargs
        _FakeStream.created += 1

    def start(self) -> None:
        _FakeStream.started += 1

    def stop(self) -> None:
        _FakeStream.stopped += 1

    def close(self) -> None:
        _FakeStream.closed += 1


def _reset_fake_stream() -> None:
    _FakeStream.created = 0
    _FakeStream.started = 0
    _FakeStream.stopped = 0
    _FakeStream.closed = 0
    _FakeStream.last_kwargs = None


def test_recorder_opens_and_closes_per_recording(monkeypatch) -> None:
    _reset_fake_stream()
    monkeypatch.setattr("moonshine_flow.audio_recorder.sd.InputStream", _FakeStream)

    recorder = AudioRecorder(
        sample_rate=16000,
        channels=1,
        dtype="float32",
        max_record_seconds=30,
    )

    recorder.start()
    recorder.stop()
    recorder.start()
    recorder.stop()

    assert _FakeStream.created == 2
    assert _FakeStream.started == 2
    assert _FakeStream.stopped == 2
    assert _FakeStream.closed == 2


def test_recorder_passes_input_device_when_configured(monkeypatch) -> None:
    _reset_fake_stream()
    monkeypatch.setattr("moonshine_flow.audio_recorder.sd.InputStream", _FakeStream)

    recorder = AudioRecorder(
        sample_rate=16000,
        channels=1,
        dtype="float32",
        max_record_seconds=30,
        input_device="MacBook Air Microphone",
    )

    recorder.start()
    recorder.stop()

    assert _FakeStream.created == 1
    assert _FakeStream.started == 1
    assert _FakeStream.stopped == 1
    assert _FakeStream.closed == 1
    assert _FakeStream.last_kwargs is not None
    assert _FakeStream.last_kwargs["device"] == "MacBook Air Microphone"


def test_stop_captures_final_callback_frames(monkeypatch) -> None:
    class _CallbackOnStopStream:
        def __init__(self, **kwargs):
            self._callback = kwargs["callback"]

        def start(self) -> None:
            return None

        def stop(self) -> None:
            tail = np.array([[0.25], [0.5]], dtype=np.float32)
            self._callback(tail, 2, None, 0)

        def close(self) -> None:
            return None

    monkeypatch.setattr("moonshine_flow.audio_recorder.sd.InputStream", _CallbackOnStopStream)

    recorder = AudioRecorder(
        sample_rate=16000,
        channels=1,
        dtype="float32",
        max_record_seconds=30,
    )

    recorder.start()
    merged = recorder.stop()

    assert merged.shape == (2, 1)
    assert np.allclose(merged[:, 0], np.array([0.25, 0.5], dtype=np.float32))


def test_recorder_uses_system_default_when_policy_is_system_default(monkeypatch) -> None:
    _reset_fake_stream()
    monkeypatch.setattr("moonshine_flow.audio_recorder.sd.InputStream", _FakeStream)

    recorder = AudioRecorder(
        sample_rate=16000,
        channels=1,
        dtype="float32",
        max_record_seconds=30,
        input_device_policy="system_default",
    )

    recorder.start()
    recorder.stop()

    assert _FakeStream.last_kwargs is not None
    assert "device" not in _FakeStream.last_kwargs


def test_recorder_prefers_external_input_device_when_policy_enabled(monkeypatch) -> None:
    _reset_fake_stream()
    monkeypatch.setattr("moonshine_flow.audio_recorder.sd.InputStream", _FakeStream)
    monkeypatch.setattr(
        "moonshine_flow.audio_recorder.sd.query_devices",
        lambda: [
            {"name": "MacBook Microphone", "max_input_channels": 1},
            {"name": "USB Microphone", "max_input_channels": 1},
        ],
    )
    monkeypatch.setattr("moonshine_flow.audio_recorder.sd.default", SimpleNamespace(device=(0, 0)))

    recorder = AudioRecorder(
        sample_rate=16000,
        channels=1,
        dtype="float32",
        max_record_seconds=30,
        input_device_policy="external_preferred",
    )

    recorder.start()
    recorder.stop()

    assert _FakeStream.last_kwargs is not None
    assert _FakeStream.last_kwargs["device"] == 1


def test_recorder_external_policy_falls_back_to_default_when_no_candidate(monkeypatch) -> None:
    _reset_fake_stream()
    monkeypatch.setattr("moonshine_flow.audio_recorder.sd.InputStream", _FakeStream)
    monkeypatch.setattr(
        "moonshine_flow.audio_recorder.sd.query_devices",
        lambda: [{"name": "MacBook Microphone", "max_input_channels": 1}],
    )
    monkeypatch.setattr("moonshine_flow.audio_recorder.sd.default", SimpleNamespace(device=(0, 0)))

    recorder = AudioRecorder(
        sample_rate=16000,
        channels=1,
        dtype="float32",
        max_record_seconds=30,
        input_device_policy="external_preferred",
    )

    recorder.start()
    recorder.stop()

    assert _FakeStream.last_kwargs is not None
    assert "device" not in _FakeStream.last_kwargs


def test_explicit_input_device_takes_priority_over_policy(monkeypatch) -> None:
    _reset_fake_stream()
    monkeypatch.setattr("moonshine_flow.audio_recorder.sd.InputStream", _FakeStream)
    monkeypatch.setattr(
        "moonshine_flow.audio_recorder.sd.query_devices",
        lambda: [
            {"name": "MacBook Microphone", "max_input_channels": 1},
            {"name": "USB Microphone", "max_input_channels": 1},
        ],
    )
    monkeypatch.setattr("moonshine_flow.audio_recorder.sd.default", SimpleNamespace(device=(0, 0)))

    recorder = AudioRecorder(
        sample_rate=16000,
        channels=1,
        dtype="float32",
        max_record_seconds=30,
        input_device="Built-in Microphone",
        input_device_policy="external_preferred",
    )

    recorder.start()
    recorder.stop()

    assert _FakeStream.last_kwargs is not None
    assert _FakeStream.last_kwargs["device"] == "Built-in Microphone"


def test_playback_friendly_policy_avoids_bluetooth_default_input(monkeypatch) -> None:
    _reset_fake_stream()
    monkeypatch.setattr("moonshine_flow.audio_recorder.sd.InputStream", _FakeStream)
    monkeypatch.setattr(
        "moonshine_flow.audio_recorder.sd.query_devices",
        lambda: [
            {"name": "Keiju AirPods", "max_input_channels": 1},
            {"name": "MacBook Microphone", "max_input_channels": 1},
        ],
    )
    monkeypatch.setattr("moonshine_flow.audio_recorder.sd.default", SimpleNamespace(device=(0, 0)))

    recorder = AudioRecorder(
        sample_rate=16000,
        channels=1,
        dtype="float32",
        max_record_seconds=30,
        input_device_policy="playback_friendly",
    )

    recorder.start()
    recorder.stop()

    assert _FakeStream.last_kwargs is not None
    assert _FakeStream.last_kwargs["device"] == 1


def test_playback_friendly_policy_keeps_non_bluetooth_default_input(monkeypatch) -> None:
    _reset_fake_stream()
    monkeypatch.setattr("moonshine_flow.audio_recorder.sd.InputStream", _FakeStream)
    monkeypatch.setattr(
        "moonshine_flow.audio_recorder.sd.query_devices",
        lambda: [
            {"name": "MacBook Microphone", "max_input_channels": 1},
            {"name": "Keiju AirPods", "max_input_channels": 1},
        ],
    )
    monkeypatch.setattr("moonshine_flow.audio_recorder.sd.default", SimpleNamespace(device=(0, 0)))

    recorder = AudioRecorder(
        sample_rate=16000,
        channels=1,
        dtype="float32",
        max_record_seconds=30,
        input_device_policy="playback_friendly",
    )

    recorder.start()
    recorder.stop()

    assert _FakeStream.last_kwargs is not None
    assert "device" not in _FakeStream.last_kwargs


def test_callback_stop_resets_recording_state(monkeypatch) -> None:
    monkeypatch.setattr("moonshine_flow.audio_recorder.sd.InputStream", _FakeStream)

    recorder = AudioRecorder(
        sample_rate=16000,
        channels=1,
        dtype="float32",
        max_record_seconds=1,
    )

    recorder.start()

    chunk = np.ones((16000, 1), dtype=np.float32)
    with pytest.raises(audio_recorder_module.sd.CallbackStop):
        recorder._callback(chunk, 16000, None, 0)

    assert recorder.is_recording is False
