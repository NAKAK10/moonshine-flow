# moonshine-flow

macOS向けの Push-to-talk 文字起こしデーモンです。
グローバルホットキーを押している間だけ録音し、離したら Moonshine で文字起こししてアクティブアプリへ貼り付けます。
音声認識には公式リポジトリの Moonshine を利用しています: https://github.com/moonshine-ai/moonshine

[English](./README.md)

詳細な運用メモ、トラブルシュート、完全なコマンド/設定リファレンスは [README.llm.md](./README.llm.md) を参照してください。

## For LLM Agents
インストールガイドを取得して、それに従ってください:

```bash
curl -s https://raw.githubusercontent.com/NAKAK10/moonshine-flow/main/README.llm.md
```

## クイックスタート
```bash
brew install moonshine-flow
moonshine-flow doctor
moonshine-flow check-permissions --request
moonshine-flow run
```
`mflow` は短縮エイリアスなので、`mflow doctor` / `mflow run` も同じように使えます。

## コマンド一覧
### 主要コマンド
| コマンド | 説明 |
| --- | --- |
| `moonshine-flow init` | 現在値をデフォルトとして `config.toml` を対話的に編集します。 |
| `moonshine-flow run` | バックグラウンドデーモンを起動します。 |
| `moonshine-flow install-launch-agent` | 初回セットアップ用: launchd エージェントをインストールします。 |
| `moonshine-flow restart-launch-agent` | 新しく許可した macOS 権限を反映するために launchd エージェントを再起動します。 |

コマンドの全一覧とオプション:
- `moonshine-flow --help`
- `moonshine-flow <command> --help`

## インストール（Homebrew）
### 最短（推奨）
```bash
./scripts/install_brew.sh
```

### 手動
```bash
brew install moonshine-flow
```

更新・削除:
```bash
brew upgrade moonshine-flow
brew uninstall moonshine-flow
```
