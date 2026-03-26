"""Granite STT backend implemented with Transformers."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import numpy as np

from ptarmigan_flow.stt.base import SpeechToTextBackend
from ptarmigan_flow.text_processing.interfaces import NoopTextPostProcessor, TextPostProcessor
from ptarmigan_flow.text_processing.normalizer import normalize_transcript_text

LOGGER = logging.getLogger(__name__)

_DEFAULT_PROMPT = "<|audio|>can you transcribe the speech into a written format?"


@dataclass(slots=True)
class GraniteTransformersSettings:
    model_id: str
    language: str
    trailing_silence_seconds: float


class GraniteTransformersSTTBackend(SpeechToTextBackend):
    """Transcribe audio using Granite speech models through Transformers."""

    def __init__(
        self,
        settings: GraniteTransformersSettings,
        *,
        post_processor: TextPostProcessor | None = None,
    ) -> None:
        self._settings = settings
        self._post_processor = post_processor or NoopTextPostProcessor()
        self._processor: Any | None = None
        self._tokenizer: Any | None = None
        self._model: Any | None = None
        self._torch: Any | None = None
        self._target_sample_rate = 16000

    @staticmethod
    def _ensure_dependencies() -> tuple[Any, Any, Any]:
        try:
            import torch
        except Exception as exc:  # pragma: no cover - optional runtime dependency
            raise RuntimeError("torch package is required for granite transformers backend") from exc

        try:
            from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor
        except Exception as exc:  # pragma: no cover - optional runtime dependency
            raise RuntimeError(
                "transformers>=4.52.1 is required for granite transformers backend"
            ) from exc

        return torch, AutoModelForSpeechSeq2Seq, AutoProcessor

    def preflight_model(self) -> str:
        if self._processor is not None and self._model is not None and self._tokenizer is not None:
            return "granite-transformers"

        torch, AutoModelForSpeechSeq2Seq, AutoProcessor = self._ensure_dependencies()
        processor = AutoProcessor.from_pretrained(self._settings.model_id)
        model = self._load_model(AutoModelForSpeechSeq2Seq, torch)
        tokenizer = getattr(processor, "tokenizer", None)
        if tokenizer is None:
            raise RuntimeError("Granite processor is missing tokenizer")

        feature_extractor = getattr(processor, "feature_extractor", None)
        sampling_rate = int(getattr(feature_extractor, "sampling_rate", 16000))
        self._processor = processor
        self._model = model
        self._tokenizer = tokenizer
        self._torch = torch
        self._target_sample_rate = sampling_rate if sampling_rate > 0 else 16000
        eval_fn = getattr(self._model, "eval", None)
        if callable(eval_fn):
            eval_fn()
        return "granite-transformers"

    def _ensure_ready(self) -> None:
        if self._processor is not None and self._model is not None and self._tokenizer is not None:
            return
        self.preflight_model()

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        if audio.size == 0:
            return ""
        self._ensure_ready()
        assert self._processor is not None
        assert self._tokenizer is not None
        assert self._model is not None
        assert self._torch is not None

        mono = self._to_mono_float32(audio)
        mono = self._append_trailing_silence(mono, sample_rate=sample_rate)
        if sample_rate != self._target_sample_rate:
            mono = self._resample_linear(
                mono,
                src_rate=sample_rate,
                dst_rate=self._target_sample_rate,
            )

        prompt = self._build_prompt(self._tokenizer)
        try:
            model_inputs = self._processor(
                prompt,
                mono,
                sampling_rate=self._target_sample_rate,
                return_tensors="pt",
            )
        except TypeError:
            model_inputs = self._processor(
                prompt,
                mono,
                return_tensors="pt",
            )

        model_inputs = self._move_inputs_to_runtime(model_inputs)
        model_outputs = self._generate(model_inputs)
        output_text = self._decode_generated(model_outputs, model_inputs)
        normalized = normalize_transcript_text(output_text)
        if not normalized:
            return ""
        return self._post_processor.apply(normalized)

    def transcribe_stream(self, audio: np.ndarray, sample_rate: int) -> Iterator[str]:
        text = self.transcribe(audio, sample_rate)
        if text:
            yield text

    def supports_realtime_input(self) -> bool:
        return False

    def maybe_release_idle_resources(self) -> None:
        return None

    def runtime_status(self) -> str:
        return f"🚀 Backend ready (no external server): {self.backend_summary()}"

    @staticmethod
    def _build_prompt(tokenizer: Any) -> str:
        apply_chat_template = getattr(tokenizer, "apply_chat_template", None)
        if not callable(apply_chat_template):
            raise RuntimeError("Granite tokenizer does not support chat template generation")
        chat = [
            {
                "role": "user",
                "content": _DEFAULT_PROMPT,
            }
        ]
        return str(apply_chat_template(chat, tokenize=False, add_generation_prompt=True))

    @staticmethod
    def _to_mono_float32(audio: np.ndarray) -> np.ndarray:
        if audio.ndim == 2:
            return np.mean(audio, axis=1).astype(np.float32, copy=False)
        return audio.astype(np.float32, copy=False)

    def _append_trailing_silence(self, audio: np.ndarray, *, sample_rate: int) -> np.ndarray:
        trailing = max(0.0, min(1.0, float(self._settings.trailing_silence_seconds)))
        trailing_samples = int(sample_rate * trailing)
        if trailing_samples <= 0:
            return audio
        return np.concatenate((audio, np.zeros(trailing_samples, dtype=np.float32)))

    @staticmethod
    def _resample_linear(audio: np.ndarray, *, src_rate: int, dst_rate: int) -> np.ndarray:
        if src_rate <= 0 or dst_rate <= 0 or audio.size == 0:
            return audio
        dst_len = int(round(audio.size * (dst_rate / src_rate)))
        if dst_len <= 1:
            return audio
        src_x = np.linspace(0.0, 1.0, num=audio.size, endpoint=True)
        dst_x = np.linspace(0.0, 1.0, num=dst_len, endpoint=True)
        return np.interp(dst_x, src_x, audio).astype(np.float32, copy=False)

    def _load_model(self, model_class: Any, torch: Any) -> Any:
        if bool(torch.cuda.is_available()):
            try:
                model = model_class.from_pretrained(
                    self._settings.model_id,
                    device_map="auto",
                    torch_dtype=torch.bfloat16,
                )
            except Exception as exc:
                if not self._is_accelerate_required_error(exc):
                    raise
                LOGGER.warning(
                    "accelerate is not installed; loading Granite without device_map=auto"
                )
                model = model_class.from_pretrained(
                    self._settings.model_id,
                    torch_dtype=torch.bfloat16,
                )
                to_fn = getattr(model, "to", None)
                if callable(to_fn):
                    model = to_fn("cuda")
            return model

        try:
            model = model_class.from_pretrained(
                self._settings.model_id,
                device_map="cpu",
            )
        except Exception as exc:
            if not self._is_accelerate_required_error(exc):
                raise
            LOGGER.warning(
                "accelerate is not installed; loading Granite without device_map=cpu"
            )
            model = model_class.from_pretrained(self._settings.model_id)
        to_fn = getattr(model, "to", None)
        if callable(to_fn):
            model = to_fn("cpu")
        return model

    @staticmethod
    def _is_accelerate_required_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return "accelerate" in message and "device_map" in message

    def _move_inputs_to_runtime(self, model_inputs: Any) -> Any:
        assert self._model is not None
        to_fn = getattr(model_inputs, "to", None)
        if not callable(to_fn):
            return model_inputs
        model_device = getattr(self._model, "device", None)
        model_dtype = getattr(self._model, "dtype", None)
        if model_device is None:
            return model_inputs
        try:
            if model_dtype is not None:
                return model_inputs.to(model_device, dtype=model_dtype)
            return model_inputs.to(model_device)
        except TypeError:
            return model_inputs.to(model_device)

    def _generate(self, model_inputs: Any) -> Any:
        assert self._model is not None
        return self._model.generate(
            **model_inputs,
            max_new_tokens=200,
            do_sample=False,
            num_beams=1,
        )

    def _decode_generated(self, model_outputs: Any, model_inputs: Any) -> str:
        assert self._tokenizer is not None
        input_ids = None
        if isinstance(model_inputs, dict):
            input_ids = model_inputs.get("input_ids")
        else:
            input_ids = getattr(model_inputs, "input_ids", None)
        if input_ids is not None:
            num_input_tokens = int(input_ids.shape[-1])
            new_tokens = model_outputs[:, num_input_tokens:]
        else:
            new_tokens = model_outputs
        decoded = self._tokenizer.batch_decode(
            new_tokens,
            add_special_tokens=False,
            skip_special_tokens=True,
        )
        if not decoded:
            return ""
        return str(decoded[0])

    def backend_summary(self) -> str:
        return (
            "backend=granite-transformers "
            f"model={self._settings.model_id} "
            f"language={self._settings.language}"
        )

    def close(self) -> None:
        self._processor = None
        self._tokenizer = None
        self._model = None
        self._torch = None
