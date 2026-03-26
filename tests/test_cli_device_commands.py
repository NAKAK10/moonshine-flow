from __future__ import annotations

import argparse

import ptarmigan_flow.presentation.cli.commands as commands
from ptarmigan_flow.config import load_config, write_config


def test_cmd_list_devices_saves_selected_device_name(tmp_path, monkeypatch) -> None:
    cfg_path = tmp_path / "config.toml"

    monkeypatch.setattr(commands, "_is_interactive_session", lambda: True)
    monkeypatch.setattr(
        commands,
        "_query_input_devices",
        lambda: ([{"index": 7, "name": "USB Desk Mic", "max_input_channels": 1}], 7),
    )
    monkeypatch.setattr("builtins.input", lambda _prompt="": "1")

    result = commands.cmd_list_devices(argparse.Namespace(config=str(cfg_path)))

    assert result == 0
    loaded = load_config(cfg_path)
    assert loaded.audio.input_device == "USB Desk Mic"


def test_cmd_list_devices_blank_input_keeps_current_named_device(tmp_path, monkeypatch) -> None:
    cfg_path = tmp_path / "config.toml"
    config = load_config(cfg_path)
    config.audio.input_device = "USB Desk Mic"
    write_config(cfg_path, config)

    monkeypatch.setattr(commands, "_is_interactive_session", lambda: True)
    monkeypatch.setattr(
        commands,
        "_query_input_devices",
        lambda: (
            [
                {"index": 2, "name": "Built-in Mic", "max_input_channels": 1},
                {"index": 5, "name": "USB Desk Mic", "max_input_channels": 1},
            ],
            2,
        ),
    )
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")

    result = commands.cmd_list_devices(argparse.Namespace(config=str(cfg_path)))

    assert result == 0
    loaded = load_config(cfg_path)
    assert loaded.audio.input_device == "USB Desk Mic"
