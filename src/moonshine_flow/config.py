"""Configuration loading and validation."""

from __future__ import annotations

import shutil
import tomllib
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ModelSize(StrEnum):
    """Supported Moonshine model sizes."""

    TINY = "tiny"
    BASE = "base"


class OutputMode(StrEnum):
    """Supported output modes."""

    CLIPBOARD_PASTE = "clipboard_paste"


class HotkeyConfig(BaseModel):
    """Hotkey configuration."""

    key: str = "right_cmd"


class AudioConfig(BaseModel):
    """Audio capture configuration."""

    sample_rate: int = 16000
    channels: int = 1
    dtype: str = "float32"
    max_record_seconds: int = 30
    input_device: str | int | None = None


class ModelConfig(BaseModel):
    """Model configuration."""

    size: ModelSize = ModelSize.BASE
    language: str = "auto"
    device: str = "mps"


class OutputConfig(BaseModel):
    """Output injection configuration."""

    mode: OutputMode = OutputMode.CLIPBOARD_PASTE
    paste_shortcut: str = "cmd+v"


class RuntimeConfig(BaseModel):
    """Runtime configuration."""

    log_level: str = "INFO"
    notify_on_error: bool = True


class AppConfig(BaseModel):
    """Top-level app configuration."""

    hotkey: HotkeyConfig = Field(default_factory=HotkeyConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)


def default_config_path() -> Path:
    """Return default user config path."""
    return Path("~/.config/moonshine-flow/config.toml").expanduser()


def _dump_toml(data: dict[str, Any]) -> str:
    """Serialize TOML without requiring optional dependencies."""
    try:
        import tomli_w

        return tomli_w.dumps(data)
    except Exception:
        input_device = data["audio"].get("input_device")
        if input_device is None:
            input_device_line = ""
        elif isinstance(input_device, str):
            input_device_line = f"input_device = \"{input_device}\"\\n"
        else:
            input_device_line = f"input_device = {input_device}\\n"

        return (
            "[hotkey]\n"
            f"key = \"{data['hotkey']['key']}\"\n\n"
            "[audio]\n"
            f"sample_rate = {data['audio']['sample_rate']}\n"
            f"channels = {data['audio']['channels']}\n"
            f"dtype = \"{data['audio']['dtype']}\"\n"
            f"max_record_seconds = {data['audio']['max_record_seconds']}\n"
            f"{input_device_line}\n"
            "[model]\n"
            f"size = \"{data['model']['size']}\"\n"
            f"language = \"{data['model']['language']}\"\n"
            f"device = \"{data['model']['device']}\"\n\n"
            "[output]\n"
            f"mode = \"{data['output']['mode']}\"\n"
            f"paste_shortcut = \"{data['output']['paste_shortcut']}\"\n\n"
            "[runtime]\n"
            f"log_level = \"{data['runtime']['log_level']}\"\n"
            f"notify_on_error = {str(data['runtime']['notify_on_error']).lower()}\n"
        )


def _to_primitive(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _to_primitive(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_primitive(item) for item in value]
    return value


def write_example_config(path: Path) -> None:
    """Write an example config file."""
    default_cfg = AppConfig()
    if hasattr(default_cfg, "model_dump"):
        cfg = default_cfg.model_dump(mode="json")
    else:
        cfg = default_cfg.dict()
    cfg = _to_primitive(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump_toml(cfg), encoding="utf-8")


def ensure_config_exists(path: Path) -> None:
    """Ensure config file exists at the path."""
    if path.exists():
        return

    bundled = Path(__file__).resolve().parents[2] / "config.example.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    if bundled.exists():
        shutil.copyfile(bundled, path)
        return

    write_example_config(path)


def load_config(path: Path | None = None) -> AppConfig:
    """Load configuration from TOML."""
    config_path = path or default_config_path()
    ensure_config_exists(config_path)
    raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    if hasattr(AppConfig, "model_validate"):
        return AppConfig.model_validate(raw)
    return AppConfig.parse_obj(raw)
