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

### アーキテクチャ互換（Apple Silicon / Intel）
- `moonshine-flow` は起動時に runtime の自己診断を行い、`moonshine_voice/libmoonshine.dylib` の読み込み可否まで検証します。
- Apple Silicon (`arm64`) で `/usr/local` Homebrew を使っている場合、x86_64 Python runtime と arm64 dylib が衝突することがあります。
- 衝突時は `$(brew --prefix)/var/moonshine-flow/.venv-<arch>` を再構築し、それでも失敗する場合は `/opt/homebrew` 側の `python@3.11` と `uv` へフォールバックを試行します。
- `/opt/homebrew` 側に `python@3.11` と `uv` が無い場合は、エラーメッセージに表示された手順に従って導入してください。

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
- `incompatible architecture` が出る:
  1. `moonshine-flow doctor` で `OS machine` / `Python machine` を確認。
  2. Apple Silicon なら arm64 toolchain を用意（例: `/opt/homebrew/bin/brew install python@3.11 uv`）。
  3. `brew reinstall moonshine-flow` 後に再実行。
- 貼り付けできない: Accessibility 許可を確認。
- ホットキーが反応しない: Input Monitoring 許可を確認。
- 録音できない: Microphone 許可を確認。

## 開発参加（最小）
前提:
- macOS（Apple Silicon / arm64）
- Python 3.11
- `uv`

### clone 後の環境確認（Python）
```bash
git clone https://github.com/NAKAK10/moonshine-flow.git
cd moonshine-flow
```

1) Python バージョンとアーキ確認:
```bash
python3.11 -V
python3.11 -c "import platform; print(platform.machine())"
```

2) 依存インストール:
```bash
uv sync --extra dev
```

3) ランタイム診断:
```bash
uv run moonshine-flow doctor
```
`OS machine` と `Python machine` が一致していることを確認してください。  
Apple Silicon で `Python machine: x86_64` の場合は Rosetta 実行です。

4) Moonshine ライブラリのロード確認:
```bash
uv run python -c "import ctypes, moonshine_voice; from pathlib import Path; lib = Path(moonshine_voice.__file__).resolve().with_name('libmoonshine.dylib'); ctypes.CDLL(str(lib)); print('moonshine dylib ok')"
```

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
