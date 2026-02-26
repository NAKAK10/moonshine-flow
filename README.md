# moonshine-flow

Push-to-talk transcription daemon for macOS.
Hold a global hotkey to record, release to transcribe with Moonshine, then paste text into the active app.

## Features
- Global key monitoring with low idle CPU usage.
- Press-and-hold recording in memory.
- Release-to-transcribe pipeline using [moonshine-ai/moonshine](https://github.com/moonshine-ai/moonshine).
- Apple Silicon `mps` preference with CPU fallback.
- Clipboard + `Cmd+V` text injection into the active window.
- launchd auto-start support.

## Requirements
- macOS (Apple Silicon / arm64 required for Moonshine transcription)
- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/)

## Install with Homebrew (tap)

### 日本語
安定版（最初のGitHub Release以降）:
```bash
brew tap MadHatterNakashima/moonshine-flow https://github.com/MadHatterNakashima/moonshine-flow
brew install moonshine-flow
```

最新版（mainブランチ）:
```bash
brew tap MadHatterNakashima/moonshine-flow https://github.com/MadHatterNakashima/moonshine-flow
brew install --HEAD moonshine-flow
```

更新/削除:
```bash
brew upgrade moonshine-flow
brew reinstall --HEAD moonshine-flow
brew uninstall moonshine-flow
```

### Stable install (after first GitHub Release)
```bash
brew tap MadHatterNakashima/moonshine-flow https://github.com/MadHatterNakashima/moonshine-flow
brew install moonshine-flow
```

### HEAD install (latest main branch)
```bash
brew tap MadHatterNakashima/moonshine-flow https://github.com/MadHatterNakashima/moonshine-flow
brew install --HEAD moonshine-flow
```

Notes:
- Stable formula fields (`url`, `sha256`, `version`) are auto-updated when a GitHub Release is published.
- Before the first Release, use `--HEAD`.
- Installation runs `uv sync --frozen` during formula install.
- Update stable package: `brew upgrade moonshine-flow`
- Reinstall HEAD package: `brew reinstall --HEAD moonshine-flow`
- Uninstall: `brew uninstall moonshine-flow`

## Quick Start (English)

### 1. Install dependencies
```bash
uv sync
```

### 2. Check environment and permissions
```bash
uv run moonshine-flow doctor
uv run moonshine-flow check-permissions
uv run moonshine-flow check-permissions --request
```

Important on Apple Silicon:
- `doctor` should show `Python machine: arm64`.
- If it shows `x86_64`, your Python is running via Rosetta and Moonshine packages may not install.
- Switch to an arm64 shell/interpreter before running `uv sync`.

Example fix (pyenv users):
```bash
arch -arm64 pyenv install 3.11.11
arch -arm64 pyenv local 3.11.11
rm -rf .venv
arch -arm64 uv sync
```

Required macOS permissions:
- Microphone
- Accessibility
- Input Monitoring

If permissions are missing, run once with `--request` to trigger system dialogs.

Enable them in:
`System Settings -> Privacy & Security`

### 3. Run daemon in foreground
```bash
uv run moonshine-flow run
```

Default hotkey is `right_cmd`.

Flow:
1. Hold the key: recording starts.
2. Release the key: recording stops and transcription starts.
3. Result text is copied to clipboard and pasted into the focused app.

### 4. Install login auto-start (launchd)
```bash
./scripts/install_launch_agent.sh
```

Remove:
```bash
./scripts/uninstall_launch_agent.sh
```

## Configuration
Default config path:
`~/.config/moonshine-flow/config.toml`

Example:
```toml
[hotkey]
key = "right_cmd"

[audio]
sample_rate = 16000
channels = 1
dtype = "float32"
max_record_seconds = 30
# input_device = "MacBook Air Microphone"  # optional: lock to specific input device

[model]
size = "base"       # "base" or "tiny"
language = "auto"   # e.g. "ja", "en", or "auto"
device = "mps"      # "mps" or "cpu"

[output]
mode = "clipboard_paste"
paste_shortcut = "cmd+v"

[runtime]
log_level = "INFO"
notify_on_error = true
```

## Notes
- If `mps` is unavailable, the app automatically falls back to CPU.
- Set `audio.input_device` to built-in mic to avoid Bluetooth profile switching during recording.
- Some secure input fields/apps may block synthetic paste events.
- If transcription package APIs change upstream, run `uv run moonshine-flow doctor` first and verify package versions.
- Current dependency set targets Apple Silicon (`arm64`). Running under `x86_64` Python on macOS can prevent Moonshine backend installation.

---

## macOS導入手順 (日本語)

### 1. 依存関係をインストール
```bash
uv sync
```

### 2. 動作診断と権限確認
```bash
uv run moonshine-flow doctor
uv run moonshine-flow check-permissions
uv run moonshine-flow check-permissions --request
```

Apple Silicon 利用時の注意:
- `doctor` の `Python machine` が `arm64` になっていることを確認してください。
- `x86_64` と表示される場合、Rosetta の Python を使っているため Moonshine 依存が入らないことがあります。
- `uv sync` 前に arm64 のシェル/インタプリタへ切り替えてください。

修正例 (pyenv 利用時):
```bash
arch -arm64 pyenv install 3.11.11
arch -arm64 pyenv local 3.11.11
rm -rf .venv
arch -arm64 uv sync
```

必要な権限:
- マイク
- アクセシビリティ
- 入力監視 (Input Monitoring)

不足している場合は、`--request` を一度実行して許可ダイアログを表示してください。

設定場所:
`システム設定 -> プライバシーとセキュリティ`

### 3. フォアグラウンドで起動
```bash
uv run moonshine-flow run
```

デフォルトのトリガーキーは `right_cmd` です。

動作フロー:
1. キーを押している間は録音。
2. キーを離すと録音停止し、Moonshineで文字起こし。
3. 結果をクリップボードへ入れ、アクティブウィンドウに貼り付け。

### 4. ログイン時に自動起動 (launchd)
```bash
./scripts/install_launch_agent.sh
```

削除:
```bash
./scripts/uninstall_launch_agent.sh
```

## 設定ファイル
デフォルトパス:
`~/.config/moonshine-flow/config.toml`

`size` は `base` / `tiny` を設定可能です。
`language` は `auto` または `ja` などを設定できます。

## トラブルシュート
- `Input Monitoring` 未許可だとグローバルキー監視が動作しません。
- `Accessibility` 未許可だと貼り付け送信が失敗します。
- `Microphone` 未許可だと録音開始に失敗します。
- MPS 非対応時は自動で CPU にフォールバックします。
- 依存関係は Apple Silicon (`arm64`) を前提にしています。macOS で `x86_64` Python を使うと Moonshine バックエンドを導入できない場合があります。
