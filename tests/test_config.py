from pathlib import Path

from moonshine_flow.config import AppConfig, load_config, write_example_config


def test_write_example_and_load_config(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    write_example_config(cfg_path)

    loaded = load_config(cfg_path)
    assert isinstance(loaded, AppConfig)
    assert loaded.hotkey.key == "right_cmd"
    assert loaded.model.size.value in {"base", "tiny"}
    assert loaded.audio.input_device_policy.value == "playback_friendly"
    assert loaded.text.dictionary_path is None


def test_load_config_creates_missing_file(tmp_path: Path) -> None:
    cfg_path = tmp_path / "new.toml"
    loaded = load_config(cfg_path)

    assert cfg_path.exists()
    assert loaded.audio.sample_rate == 16000


def test_load_config_accepts_external_preferred_policy(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        """
[hotkey]
key = "right_cmd"

[audio]
sample_rate = 16000
channels = 1
dtype = "float32"
max_record_seconds = 30
input_device_policy = "external_preferred"

[model]
size = "base"
language = "ja"
device = "mps"

[output]
mode = "clipboard_paste"
paste_shortcut = "cmd+v"

[runtime]
log_level = "INFO"
notify_on_error = true
""".strip(),
        encoding="utf-8",
    )

    loaded = load_config(cfg_path)
    assert loaded.audio.input_device_policy.value == "external_preferred"


def test_load_config_accepts_playback_friendly_policy(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        """
[hotkey]
key = "right_cmd"

[audio]
sample_rate = 16000
channels = 1
dtype = "float32"
max_record_seconds = 30
input_device_policy = "playback_friendly"

[model]
size = "base"
language = "ja"
device = "mps"

[output]
mode = "clipboard_paste"
paste_shortcut = "cmd+v"

[runtime]
log_level = "INFO"
notify_on_error = true
""".strip(),
        encoding="utf-8",
    )

    loaded = load_config(cfg_path)
    assert loaded.audio.input_device_policy.value == "playback_friendly"
