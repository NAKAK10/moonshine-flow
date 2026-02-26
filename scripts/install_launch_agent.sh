#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${1:-$HOME/.config/moonshine-flow/config.toml}"

uv run moonshine-flow install-launch-agent --config "$CONFIG_PATH"
