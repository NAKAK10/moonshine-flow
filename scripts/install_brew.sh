#!/usr/bin/env bash
set -euo pipefail

TAP="madhatternakashima/moonshine-flow"
FORMULA="moonshine-flow"

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required. Install from https://brew.sh first." >&2
  exit 1
fi

echo "Tapping ${TAP}..."
HOMEBREW_NO_AUTO_UPDATE=1 brew tap "${TAP}" "https://github.com/MadHatterNakashima/moonshine-flow"

echo "Installing ${FORMULA}..."
if HOMEBREW_NO_AUTO_UPDATE=1 brew install "${FORMULA}"; then
  echo "Installed stable release: ${FORMULA}"
else
  echo "Stable formula unavailable yet. Installing --HEAD..."
  HOMEBREW_NO_AUTO_UPDATE=1 brew install --HEAD "${FORMULA}"
  echo "Installed HEAD release: ${FORMULA}"
fi

echo "Done. Verify with: moonshine-flow --help"
