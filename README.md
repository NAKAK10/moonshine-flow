# moonshine-flow

A push-to-talk transcription daemon for macOS.
It records only while a global hotkey is held, and when released it transcribes with Moonshine and pastes into the active app.
It uses Moonshine from the official repository: https://github.com/moonshine-ai/moonshine

[日本語](./README.ja.md)

For detailed operational notes, edge cases, troubleshooting, and full command/config reference, see [README.llm.md](./README.llm.md).

## For LLM Agents
Fetch the installation guide and follow it:

```bash
curl -s https://raw.githubusercontent.com/NAKAK10/moonshine-flow/main/README.llm.md
```

## Quickstart
```bash
brew install moonshine-flow
moonshine-flow doctor
moonshine-flow check-permissions --request
moonshine-flow run
```
`mflow` is a shorthand alias, so `mflow doctor` / `mflow run` also work.

## Command Reference
### Core Commands
| Command | Description |
| --- | --- |
| `moonshine-flow init` | Interactively edit `config.toml` with current values as defaults. |
| `moonshine-flow run` | Run the background daemon. |
| `moonshine-flow install-launch-agent` | One-time setup: install the launchd agent for auto-start at login. |
| `moonshine-flow restart-launch-agent` | Restart the launchd agent to apply newly granted macOS permissions. |

For full command list and options:
- `moonshine-flow --help`
- `moonshine-flow <command> --help`

## Installation (Homebrew)
### Fast path (recommended)
```bash
./scripts/install_brew.sh
```

### Manual
```bash
brew install moonshine-flow
```

Update / uninstall:
```bash
brew upgrade moonshine-flow
brew uninstall moonshine-flow
```
