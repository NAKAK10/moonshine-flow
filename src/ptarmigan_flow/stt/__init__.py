"""Speech-to-text backends."""

from ptarmigan_flow.stt.base import SpeechToTextBackend
from ptarmigan_flow.stt.factory import create_stt_backend, parse_stt_model

__all__ = [
    "SpeechToTextBackend",
    "create_stt_backend",
    "parse_stt_model",
]

