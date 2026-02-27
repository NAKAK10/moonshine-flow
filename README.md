# moonshine-flow

A push-to-talk transcription daemon for macOS.  
It records only while a global hotkey is held, and when released it transcribes with Moonshine and pastes into the active app.
It uses Moonshine from the official repository: https://github.com/moonshine-ai/moonshine

[日本語](./README.ja.md)

## Quickstart
```bash
./scripts/install_brew.sh
moonshine-flow doctor
moonshine-flow check-permissions --request
moonshine-flow run
```

Required macOS permissions:
- Microphone
- Accessibility
- Input Monitoring

Settings location: `System Settings -> Privacy & Security`

## Features
- Recording trigger via global key monitor
- Speech recognition with Moonshine (`moonshine-voice`)
- Paste transcribed text via clipboard + `Cmd+V`
- Auto-start at login with `launchd`

## Installation (Homebrew)
### Fast path (recommended)
```bash
./scripts/install_brew.sh
```

### Manual
```bash
brew install moonshine-flow
```

To install the latest (`main`):
```bash
brew reinstall --HEAD moonshine-flow
```

Update / uninstall:
```bash
brew upgrade moonshine-flow
brew uninstall moonshine-flow
```

Notes:
- In most cases, you do not need to specify a `brew tap` URL.
- If Homebrew auto-update causes failures in your environment, add `HOMEBREW_NO_AUTO_UPDATE=1` only when needed.
- If the runtime is broken, startup will attempt an auto-repair under `$(brew --prefix)/var/moonshine-flow`.

### Architecture compatibility (Apple Silicon / Intel)
- `moonshine-flow` performs runtime self-diagnostics at startup, including validation that `moonshine_voice/libmoonshine.dylib` can be loaded.
- On Apple Silicon (`arm64`) with Homebrew under `/usr/local`, an x86_64 Python runtime may conflict with an arm64 dylib.
- On conflict, it rebuilds `$(brew --prefix)/var/moonshine-flow/.venv-<arch>`. If that still fails, it attempts fallback to `/opt/homebrew` `python@3.11` and `uv`.
- If `/opt/homebrew` `python@3.11` and `uv` are missing, follow the steps shown in the error message.

## launchd auto-start
```bash
moonshine-flow install-launch-agent
moonshine-flow uninstall-launch-agent
```

## Config file
Default: `~/.config/moonshine-flow/config.toml`  
If missing, it is created automatically on first run.

Main settings:
- `hotkey.key`: Recording trigger key (default: `right_cmd`)
- `model.size`: `base` / `tiny`
- `model.language`: `auto` / `ja` / `en` / etc.
- `model.device`: `mps` / `cpu`

## Troubleshooting
- `bad interpreter`: rerun `moonshine-flow --help` and wait for auto-repair. If it still fails, run `brew reinstall moonshine-flow`.
- Homebrew `stable` is older than the latest tag:
  1. `brew update-reset && brew update`
  2. Check `stable` with `brew info moonshine-flow`
  3. If still old, inspect the tap formula: `brew cat moonshine-flow | sed -n '1,20p'`
  4. Temporary workaround: `brew reinstall --HEAD moonshine-flow`
- `incompatible architecture` appears:
  1. Check `OS machine` and `Python machine` with `moonshine-flow doctor`.
  2. On Apple Silicon, prepare arm64 toolchain (example: `/opt/homebrew/bin/brew install python@3.11 uv`).
  3. Reinstall and retry: `brew reinstall moonshine-flow`.
- Cannot paste: verify Accessibility permission.
- Hotkey not detected: verify Input Monitoring permission.
- Cannot record: verify Microphone permission.

## Development (minimal)
Prerequisites:
- macOS (Apple Silicon / arm64)
- Python 3.11
- `uv`

### Environment check after clone (Python)
```bash
git clone https://github.com/NAKAK10/moonshine-flow.git
cd moonshine-flow
```

1) Check Python version and architecture:
```bash
python3.11 -V
python3.11 -c "import platform; print(platform.machine())"
```

2) Install dependencies:
```bash
uv sync --extra dev
```

3) Run runtime diagnostics:
```bash
uv run moonshine-flow doctor
```
Confirm `OS machine` and `Python machine` match.  
If `Python machine: x86_64` on Apple Silicon, it is running under Rosetta.

4) Verify Moonshine library loading:
```bash
uv run python -c "import ctypes, moonshine_voice; from pathlib import Path; lib = Path(moonshine_voice.__file__).resolve().with_name('libmoonshine.dylib'); ctypes.CDLL(str(lib)); print('moonshine dylib ok')"
```

Setup:
```bash
uv sync --extra dev
```

Tests:
```bash
uv run pytest
```

Minimum files to check when making changes:
- `src/moonshine_flow/cli.py` (CLI)
- `src/moonshine_flow/homebrew_bootstrap.py` (Homebrew startup / self-repair)
- `Formula/moonshine-flow.rb` (distribution formula)
