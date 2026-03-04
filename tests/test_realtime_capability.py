from moonshine_flow.stt.realtime_capability import supports_realtime_input_model


def test_supports_realtime_input_model_for_known_ids() -> None:
    assert supports_realtime_input_model("mistralai/Voxtral-Mini-4B-Realtime-2602") is True
    assert supports_realtime_input_model("mlx-community/Voxtral-Mini-4B-Realtime-6bit") is True


def test_supports_realtime_input_model_for_unknown_id() -> None:
    assert supports_realtime_input_model("mlx-community/whisper-large-v3-turbo") is False
