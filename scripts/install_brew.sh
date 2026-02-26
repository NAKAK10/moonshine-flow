#!/usr/bin/env bash
set -euo pipefail

TAP="madhatternakashima/moonshine-flow"
TAP_URL="https://github.com/MadHatterNakashima/moonshine-flow"
FORMULA="moonshine-flow"

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required. Install from https://brew.sh first." >&2
  exit 1
fi

if brew tap | grep -qx "${TAP}"; then
  TAP_REPO="$(brew --repository "${TAP}")"
  CURRENT_REMOTE="$(git -C "${TAP_REPO}" remote get-url origin 2>/dev/null || true)"
  if [[ "${CURRENT_REMOTE}" != "${TAP_URL}" && "${CURRENT_REMOTE}" != "git@github.com:MadHatterNakashima/moonshine-flow.git" ]]; then
    echo "Tap remote mismatch detected for ${TAP}; re-tapping..."
    HOMEBREW_NO_AUTO_UPDATE=1 brew untap "${TAP}"
  fi
fi

echo "Tapping ${TAP}..."
HOMEBREW_NO_AUTO_UPDATE=1 brew tap "${TAP}" "${TAP_URL}"

echo "Installing ${FORMULA}..."
if HOMEBREW_NO_AUTO_UPDATE=1 brew install "${FORMULA}"; then
  echo "Installed stable release: ${FORMULA}"
else
  echo "Stable formula unavailable yet. Installing --HEAD..."
  HOMEBREW_NO_AUTO_UPDATE=1 brew install --HEAD "${FORMULA}"
  echo "Installed HEAD release: ${FORMULA}"
fi

moonshine-flow --help >/dev/null
echo "Done. Verified command: moonshine-flow --help"
