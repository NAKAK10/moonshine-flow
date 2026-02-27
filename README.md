# moonshine-flow

A push-to-talk transcription daemon for macOS.  
It records only while a global hotkey is held, and when released it transcribes with Moonshine and pastes into the active app.
It uses Moonshine from the official repository: https://github.com/moonshine-ai/moonshine

[日本語](./README.ja.md)

## Quickstart
```bash
brew install moonshine-flow
moonshine-flow doctor
moonshine-flow check-permissions --request
moonshine-flow run
```
`mflow` is a shorthand alias, so `mflow doctor` / `mflow run` also work.

If install fails because of tap or Homebrew environment issues, try:
```bash
./scripts/install_brew.sh
```

Required macOS permissions:
- Microphone
- Accessibility
- Input Monitoring

Settings location: `System Settings -> Privacy & Security`

## Command Reference
| Command | Description |
| --- | --- |
| `moonshine-flow -v` | Show package version and exit (release-tag based at build time). |
| `moonshine-flow --version` | Show package version and exit (release-tag based at build time). |
| `moonshine-flow run` | Run the background daemon. |
| `moonshine-flow doctor` | Print runtime diagnostics and permission status. |
| `moonshine-flow doctor --launchd-check` | Compare permission status between terminal and launchd context. |
| `moonshine-flow check-permissions` | Check required macOS permissions without prompting. |
| `moonshine-flow check-permissions --request` | Prompt for missing permissions where possible and show status. |
| `moonshine-flow install-launch-agent` | Install the launchd agent for auto-start at login (requests permissions by default). |
| `moonshine-flow install-launch-agent --allow-missing-permissions` | Install the launchd agent even if required macOS permissions are still missing. |
| `moonshine-flow install-launch-agent --no-request-permissions` | Skip permission prompt attempts and only check current permission state. |
| `moonshine-flow install-launch-agent --verbose-bootstrap` | Show detailed runtime recovery logs during launch-agent installation. |
| `moonshine-flow uninstall-launch-agent` | Remove the launchd agent. |

All commands above are also available via the `mflow` alias.

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
brew install --HEAD moonshine-flow
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
moonshine-flow install-launch-agent --verbose-bootstrap
moonshine-flow uninstall-launch-agent
```

Notes:
- `install-launch-agent` requests missing permissions by default.
- If required permissions remain missing, installation is aborted by default to avoid "hotkey works poorly / paste does not happen" states.
- Use `--allow-missing-permissions` only when you intentionally want to install anyway.
- Runtime auto-recovery output is quiet on success; use `--verbose-bootstrap` when you need full `uv sync` logs.
- On successful install, the CLI prints `Permission target (recommended)`. Use that exact path in macOS permission settings.

Recommended verification flow:
```bash
mflow install-launch-agent
mflow doctor --launchd-check
```
Confirm these lines are shown:
- `LaunchAgent plist: FOUND`
- `Permissions: OK`
- `Launchd permissions: OK`

## Config file
Default: `~/.config/moonshine-flow/config.toml`  
If missing, it is created automatically on first run.

Main settings:
- `hotkey.key`: Recording trigger key (default: `right_cmd`)
- `model.size`: `base` / `tiny`
- `model.language`: `auto` / `ja` / `en` / etc.
- `model.device`: `mps` / `cpu`

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

4) Run a daemon smoke test:
```bash
uv run moonshine-flow run
```
Press and release the configured hotkey once to verify the transcription flow, then stop with `Ctrl+C`.

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
