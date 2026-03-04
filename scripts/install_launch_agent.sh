#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${1:-$HOME/.config/ptarmigan-flow/config.toml}"

uv run ptarmigan-flow install-launch-agent --config "$CONFIG_PATH"
