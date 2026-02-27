# moonshine-flow

macOS向けの Push-to-talk 文字起こしデーモンです。  
グローバルホットキーを押している間だけ録音し、離したら Moonshine で文字起こししてアクティブアプリへ貼り付けます。
音声認識には公式リポジトリの Moonshine を利用しています: https://github.com/moonshine-ai/moonshine

[English](./README.md)

## クイックスタート
```bash
brew install moonshine-flow
moonshine-flow doctor
moonshine-flow check-permissions --request
moonshine-flow run
```
`mflow` は短縮エイリアスなので、`mflow doctor` / `mflow run` も同じように使えます。

tap や Homebrew 環境起因でインストール失敗する場合は、次を試してください:
```bash
./scripts/install_brew.sh
```

## 権限設定
設定場所: `System Settings -> Privacy & Security`

必要な macOS 権限:
- Accessibility
- Input Monitoring
- Microphone

### 一般利用（ターミナル実行）
1. 権限要求を出す:
```bash
mflow check-permissions --request
```
2. デーモンを起動する:
```bash
mflow run
```

### launch-agent 利用（ログイン時自動起動）
1. 初回セットアップのみ: launch-agent をインストールする（既定で app bundle も作成/更新）:
```bash
mflow install-launch-agent
```
2. macOS 設定で次のパスへ権限を許可する。  
`~/Applications/MoonshineFlow.app/Contents/MacOS/MoonshineFlow`
3. 権限を変更した後に launch-agent を再起動する:
```bash
mflow restart-launch-agent
```
4. ターミナル実行と launchd 実行の両方を確認する:
```bash
mflow doctor --launchd-check
```

## コマンド一覧
### 一般コマンド
| コマンド | 説明 |
| --- | --- |
| `moonshine-flow -v` | パッケージバージョンを表示して終了します（ビルド時にリリースタグから確定）。 |
| `moonshine-flow --version` | パッケージバージョンを表示して終了します（ビルド時にリリースタグから確定）。 |
| `moonshine-flow run` | バックグラウンドデーモンを起動します。 |
| `moonshine-flow doctor` | ランタイム診断と権限状態を表示します。 |
| `moonshine-flow check-permissions` | macOS 権限の状態を確認します（プロンプトなし）。 |
| `moonshine-flow check-permissions --request` | 可能な範囲で不足権限の許可を要求し、状態を表示します。 |

### launch-agent / app コマンド
| コマンド | 説明 |
| --- | --- |
| `moonshine-flow install-launch-agent` | 初回セットアップ用: launchd エージェントをインストールします（既定で launchd 実行対象の権限を確認/要求）。 |
| `moonshine-flow install-launch-agent --allow-missing-permissions` | 必須権限が不足していても launchd エージェントをインストールします。 |
| `moonshine-flow install-launch-agent --no-request-permissions` | 権限要求プロンプトを出さず、現在の権限状態だけ確認します。 |
| `moonshine-flow install-launch-agent --verbose-bootstrap` | インストール中の runtime 自動修復ログを詳細表示します。 |
| `moonshine-flow doctor --launchd-check` | ターミナル実行と launchd 実行の権限状態を比較します。 |
| `moonshine-flow restart-launch-agent` | 新しく許可した macOS 権限を反映するために launchd エージェントを再起動します。 |
| `moonshine-flow uninstall-launch-agent` | launchd エージェントを削除します。 |

上記コマンドはすべて `mflow` エイリアスでも同様に使えます。

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
brew install --HEAD moonshine-flow
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

## launchd 自動起動
launch-agent 専用の実行手順:
```bash
# 初回セットアップ
moonshine-flow install-launch-agent

# 権限変更後の反映
moonshine-flow doctor --launchd-check
moonshine-flow restart-launch-agent
moonshine-flow doctor --launchd-check

# 必要時のみ詳細ログ付きで再インストール
moonshine-flow install-launch-agent --verbose-bootstrap

# 自動起動の削除
moonshine-flow uninstall-launch-agent
```

補足:
- `install-launch-agent` は既定で不足権限の許可を要求します。
- `install-launch-agent` は launchd が実行するのと同じ実行対象で権限確認を行います。
- `install-launch-agent` は既定で `~/Applications/MoonshineFlow.app` を作成/更新し、launchd の実行コマンドにその実行ファイルを優先して設定します。
- **app bundle 差分更新**: `install-launch-agent`（および `install-app-bundle`）は、実行バイナリ・`Info.plist`・`bootstrap.json` のいずれかが変更された場合のみ上書きおよび再署名を行います。これにより CDHash が不必要に変わることを防ぎ、macOS TCC の権限バインディングが失われるのを回避します。
- 必須権限が不足している場合、長押しや貼り付けが不安定になるのを防ぐため、既定ではインストールを中断します。
- 意図的に継続したい場合だけ `--allow-missing-permissions` を使ってください。
- runtime 自動修復ログは成功時は最小表示です。`uv sync` の詳細が必要なときだけ `--verbose-bootstrap` を指定してください。
- System Settings で権限を許可した後は、`mflow restart-launch-agent` を実行して即時反映してください。
- `install-app-bundle` は上級者向けの手動コマンドで、通常運用では不要です。
- LaunchAgent は `~/Applications/MoonshineFlow.app/Contents/MacOS/MoonshineFlow` を起動し、bootstrap はその同一プロセス識別を維持したまま runtime 依存を読み込みます。
- 権限はコマンド名ではなく、実行ファイルの実体パス（および署名）単位で管理されます。launchd では `doctor` が示す推奨ターゲットを許可してください。
- Input Monitoring に `MoonshineFlow` が出ない場合は `moonshine-flow install-launch-agent --request-permissions` を再実行し、`moonshine-flow doctor --launchd-check` で確認してください。

## トラブルシューティング

### `doctor` の権限状態

| 状態 | 意味 |
| --- | --- |
| `Permissions: OK` | 全権限が許可済みで、ランタイム警告なし。 |
| `Permissions: WARN` | `--launchd-check` では全権限 OK だが、デーモンログに `pynput ... This process is not trusted!` が記録されている。app bundle が再署名され（CDHash 変化）、macOS TCC の権限バインディングが失われた可能性があります。 |
| `Permissions: INCOMPLETE` | 1つ以上の権限が未許可。System Settings で許可してください。 |

### `Permissions: WARN` — TCC 権限バインディングの喪失

`mflow doctor --launchd-check` で `Permissions: WARN (launchd check OK but runtime not trusted)` が表示された場合:

1. 現在の実行ファイルと CDHash を確認する:
```bash
mflow doctor --launchd-check
```
出力中の `App bundle CDHash` と `App bundle executable mtime` を確認してください。

2. `System Settings -> Privacy & Security` で、表示されているターゲット（`~/Applications/MoonshineFlow.app/Contents/MacOS/MoonshineFlow`）に対して Accessibility と Input Monitoring を再許可する。

3. launch-agent を再起動する:
```bash
mflow restart-launch-agent
```

4. 警告が消えたことを確認する:
```bash
mflow doctor --launchd-check
```
期待値: `Permissions: OK`

**原因**: macOS TCC は権限をコード署名（CDHash）と紐付けて管理します。`brew upgrade moonshine-flow` で Python runtime が更新されると、`install-app-bundle` は差分チェックを行い、バイナリが変化した場合のみ再署名します。その際 CDHash が変わり、古い TCC レコードが一致しなくなります。差分更新により不要な再署名は最小化されていますが、Python バイナリ自体が変わった場合は再許可が必要です。

## 設定ファイル
デフォルト: `~/.config/moonshine-flow/config.toml`  
初回実行時に存在しなければ自動作成されます。

主な設定:
- `hotkey.key`: 録音トリガーキー（既定: `right_cmd`）
- `model.size`: `base` / `tiny`
- `model.language`: `auto` / `ja` / `en` など
- `model.device`: `mps` / `cpu`

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

4) デーモンのスモークテスト:
```bash
uv run moonshine-flow run
```
設定したホットキーを一度押して離し、文字起こしフローを確認したら `Ctrl+C` で停止します。

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
