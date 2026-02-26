from pathlib import Path

from moonshine_flow.config import AppConfig, load_config, write_example_config


def test_write_example_and_load_config(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    write_example_config(cfg_path)

    loaded = load_config(cfg_path)
    assert isinstance(loaded, AppConfig)
    assert loaded.hotkey.key == "right_cmd"
    assert loaded.model.size.value in {"base", "tiny"}


def test_load_config_creates_missing_file(tmp_path: Path) -> None:
    cfg_path = tmp_path / "new.toml"
    loaded = load_config(cfg_path)

    assert cfg_path.exists()
    assert loaded.audio.sample_rate == 16000
