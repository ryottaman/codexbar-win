# CodexBar for Windows

AI コーディングツールの利用量・上限・リセット時刻を **Windows のタスクトレイに常駐表示** するツールです。

macOS 専用アプリ [CodexBar](https://github.com/steipete/CodexBar)（by [steipete](https://github.com/steipete), MIT License）の中核ロジックを、Windows / Python 向けに再実装したものです。

## 対応プロバイダー

| プロバイダー | 方式 | 状態 |
|---|---|---|
| **Claude / Claude Code** | `~/.claude/.credentials.json` の OAuth トークンで `api.anthropic.com/api/oauth/usage` を取得 | ✅ 動作確認済み |
| **OpenAI / Codex** | `~/.codex/auth.json` の OAuth トークンで `chatgpt.com/backend-api/wham/usage` を取得 | ✅ 実装済み（Codex CLI 導入時に有効化） |
| **GitHub Copilot** | `gh` CLI のトークンで `api.github.com/copilot_internal/user` を取得 | ✅ 動作確認済み（無制限プランはメーター無し・プラン表示） |
| **Gemini** | `~/.gemini/oauth_creds.json` で `cloudcode-pa.googleapis.com` を取得（トークン自動リフレッシュ） | ✅ 実装済み（Gemini CLI 認証時に有効化） |

未導入・未設定のプロバイダーは自動でスキップされます。

## 動作要件

- Windows 10 / 11
- Python 3.11 以上（`tomllib` 標準搭載のため）
- 対象ツールにログイン済みであること（Claude Code / Codex CLI）

## セットアップ

```powershell
cd $env:USERPROFILE\Desktop\codexbar-win
pip install -r requirements.txt
```

## 起動

```powershell
# 通常起動（コンソール窓あり・デバッグ用）
python main.py

# コンソール窓なしで常駐
pythonw run.pyw
```

トレイアイコンは**最も逼迫している利用枠**の使用率をリングで表示します。

- 緑: 〜70%
- 黄: 70〜90%
- 赤: 90%〜

アイコンを右クリックすると、各枠の使用率とリセットまでの残り時間、更新・終了メニューが出ます。

## Windows 起動時に自動常駐させる

```powershell
powershell -ExecutionPolicy Bypass -File install_startup.ps1
```

スタートアップフォルダにショートカットを作成します。解除はそのショートカットを削除するだけです。

## 設定（config.toml）

```toml
interval = 300                              # 更新間隔（秒）
enabled = ["claude", "codex", "copilot", "gemini"]  # 表示するプロバイダー
```

更新間隔・表示するツールはトレイメニューからも変更でき、変更内容は `config.toml` に自動保存されます。

## プロバイダーの追加方法

1. `providers/<name>.py` を作り、`fetch() -> UsageResult` を実装する
2. `providers/__init__.py` の `REGISTRY` に登録する

`UsageResult` / `Meter` の型は `providers/base.py` を参照してください。本家 CodexBar には他にも多数の媒体の取得ロジックがあり、同じパターンで移植できます。

## 免責事項

- 本ツールは各 AI 媒体の**公式に文書化されていない内部エンドポイント**を利用します。これらの利用は各社の利用規約で明示的に許可されたものではなく、仕様変更や遮断でいつでも動かなくなる可能性があります。
- 想定用途は**利用者自身が自分の利用状況を確認すること**です。業務上の請求根拠や第三者への提供には使わないでください。
- 認証情報（OAuth トークン等）は**ローカルの既存ファイルを読むだけ**で、外部への送信・保存は行いません。取得先は各媒体の公式ドメインのみです。
- 表示されるコストは公開価格からの**概算**であり、実際の請求額とは一致しません。
- **利用は自己責任でお願いします。** 本ツールの使用に起因するいかなる損害についても作者は責任を負いません。

## ライセンス / 出典

本ツールは [CodexBar](https://github.com/steipete/CodexBar)（MIT License, Copyright © 2026 Peter Steinberger）の設計・取得ロジックを参考に再実装しています。詳細は [ATTRIBUTION.md](./ATTRIBUTION.md) を、ライセンス全文は [LICENSE](./LICENSE) を参照してください。
