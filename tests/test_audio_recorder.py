from __future__ import annotations

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
