# moonshine-flow

macOS向けの Push-to-talk 文字起こしデーモンです。  
グローバルホットキーを押している間だけ録音し、離したら Moonshine で文字起こししてアクティブアプリへ貼り付けます。

## できること
- グローバルキー監視で録音トリガー
- Moonshine (`moonshine-voice`) で音声認識
- クリップボード + `Cmd+V` で結果を貼り付け
- `launchd` でログイン時自動起動

## インストール（Homebrew）
### 最短（推奨）
```bash
./scripts/install_brew.sh
```

### 手動
```bash
brew install moonshine-flow
```

最新版（`main`）を入れる場合:
```bash
brew reinstall --HEAD moonshine-flow
```

更新・削除:
```bash
brew upgrade moonshine-flow
brew uninstall moonshine-flow
```

補足:
- `brew tap` の URL 指定は通常不要です。
- Homebrew auto-update が原因で失敗する環境では、必要時のみ `HOMEBREW_NO_AUTO_UPDATE=1` を付けてください。
- ランタイムが壊れた場合は、起動時に `$(brew --prefix)/var/moonshine-flow` 配下を自動修復します。

## 初期セットアップ
```bash
moonshine-flow doctor
moonshine-flow check-permissions --request
moonshine-flow run
```

必要な macOS 権限:
- Microphone
- Accessibility
- Input Monitoring

設定場所: `System Settings -> Privacy & Security`

## launchd 自動起動
```bash
moonshine-flow install-launch-agent
moonshine-flow uninstall-launch-agent
```

## 設定ファイル
デフォルト: `~/.config/moonshine-flow/config.toml`  
初回実行時に存在しなければ自動作成されます。

主な設定:
- `hotkey.key`: 録音トリガーキー（既定: `right_cmd`）
- `model.size`: `base` / `tiny`
- `model.language`: `auto` / `ja` / `en` など
- `model.device`: `mps` / `cpu`

## トラブルシュート
- `bad interpreter` が出る: `moonshine-flow --help` を再実行して自己修復を待つ。解消しない場合は `brew reinstall moonshine-flow`。
- 貼り付けできない: Accessibility 許可を確認。
- ホットキーが反応しない: Input Monitoring 許可を確認。
- 録音できない: Microphone 許可を確認。

## 開発参加（最小）
前提:
- macOS（Apple Silicon / arm64）
- Python 3.11
- `uv`

セットアップ:
```bash
uv sync --extra dev
```

テスト:
```bash
uv run pytest
```

変更時に最低限見るファイル:
- `src/moonshine_flow/cli.py`（CLI）
- `src/moonshine_flow/homebrew_bootstrap.py`（Homebrew 起動・自己修復）
- `Formula/moonshine-flow.rb`（配布定義）
