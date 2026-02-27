#!/usr/bin/env bash
set -euo pipefail

TAP="nakak10/moonshine-flow"
TAP_URL="https://github.com/NAKAK10/moonshine-flow"
FORMULA="moonshine-flow"
EXPECTED_REPO="nakak10/moonshine-flow"
TAP_EXISTS=0
BREW_PREFIX=""

print_permission_fix() {
  local -a dirs=("$@")
  if [[ "${#dirs[@]}" -eq 0 ]]; then
    return
  fi

  echo "The following directories are not writable by your user:" >&2
  printf '  %s\n' "${dirs[@]}" >&2
  echo >&2
  echo "Fix with:" >&2
  echo "  sudo chown -R \"$(whoami)\" ${dirs[*]}" >&2
  echo "  chmod u+w ${dirs[*]}" >&2
}

preflight_checks() {
  local arch
  arch="$(uname -m)"
  BREW_PREFIX="$(brew --prefix)"

  if [[ "${arch}" == "arm64" && "${BREW_PREFIX}" == "/usr/local" ]]; then
    echo "Warning: Apple Silicon detected with Homebrew prefix /usr/local." >&2
    echo "This setup is prone to permission issues. Recommended prefix is /opt/homebrew." >&2
    echo "Migration guide: https://docs.brew.sh/Installation" >&2
    echo >&2
  fi

  local -a required_dirs=(
    "${HOME}/Library/Caches/Homebrew"
    "${HOME}/Library/Logs/Homebrew"
    "${BREW_PREFIX}"
    "${BREW_PREFIX}/Cellar"
    "${BREW_PREFIX}/bin"
    "${BREW_PREFIX}/etc"
    "${BREW_PREFIX}/lib"
    "${BREW_PREFIX}/opt"
    "${BREW_PREFIX}/sbin"
    "${BREW_PREFIX}/share"
    "${BREW_PREFIX}/var/homebrew"
  )
  local -a unwritable=()
  local d
  for d in "${required_dirs[@]}"; do
    if [[ -e "${d}" && ! -w "${d}" ]]; then
      unwritable+=("${d}")
    fi
  done

  if [[ "${#unwritable[@]}" -gt 0 ]]; then
    print_permission_fix "${unwritable[@]}"
    exit 1
  fi
}

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required. Install from https://brew.sh first." >&2
  exit 1
fi

preflight_checks

if brew tap | grep -qx "${TAP}"; then
  TAP_EXISTS=1
  TAP_REPO="$(brew --repository "${TAP}")"
  CURRENT_REMOTE="$(git -C "${TAP_REPO}" remote get-url origin 2>/dev/null || true)"
  CURRENT_REPO_SLUG="$(printf '%s' "${CURRENT_REMOTE}" \
    | sed -E 's#^(git@github\.com(\.private)?:|https://github\.com/)##; s#\.git$##' \
    | tr '[:upper:]' '[:lower:]')"
  TAP_HAS_CONFLICTS=0
  if git -C "${TAP_REPO}" ls-files -u | grep -q .; then
    TAP_HAS_CONFLICTS=1
  fi

  if [[ -z "${CURRENT_REPO_SLUG}" || "${CURRENT_REPO_SLUG}" != "${EXPECTED_REPO}" || "${TAP_HAS_CONFLICTS}" -eq 1 ]]; then
    if [[ "${TAP_HAS_CONFLICTS}" -eq 1 ]]; then
      echo "Tap repository has unresolved merge conflicts; re-tapping..."
    else
      echo "Tap remote mismatch detected for ${TAP}; re-tapping..."
    fi
    HOMEBREW_NO_AUTO_UPDATE=1 brew untap "${TAP}"
    TAP_EXISTS=0
  fi
fi

if [[ "${TAP_EXISTS}" -eq 0 ]]; then
  echo "Tapping ${TAP}..."
  HOMEBREW_NO_AUTO_UPDATE=1 brew tap "${TAP}" "${TAP_URL}"
else
  echo "Tap ${TAP} is already configured."
fi

echo "Installing ${FORMULA}..."
if HOMEBREW_NO_AUTO_UPDATE=1 brew install "${FORMULA}"; then
  echo "Installed stable release: ${FORMULA}"
else
  if HOMEBREW_NO_AUTO_UPDATE=1 brew info "${FORMULA}" >/dev/null 2>&1; then
    echo "Stable install failed. Resolve the Homebrew error above and retry." >&2
    exit 1
  fi
  echo "Stable formula unavailable yet. Installing --HEAD..."
  HOMEBREW_NO_AUTO_UPDATE=1 brew install --HEAD "${FORMULA}"
  echo "Installed HEAD release: ${FORMULA}"
fi

moonshine-flow --help >/dev/null
echo "Done. Verified command: moonshine-flow --help"
