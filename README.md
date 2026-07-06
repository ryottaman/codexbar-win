# CodexBar for Windows

AI コーディングツールの利用量・上限・リセット時刻を **Windows のタスクトレイに常駐表示** するツールです。

macOS 専用アプリ [CodexBar](https://github.com/steipete/CodexBar)（by [steipete](https://github.com/steipete), MIT License）の中核ロジックを、Windows / Python 向けに再実装したものです。

## 機能

- **トレイアイコン**: 最も逼迫している利用枠の使用率をリングで常時表示（緑 →70%→ 黄 →90%→ 赤）
- **パネル UI**（アイコンをクリックで開閉）:
  - **概要タブ**: 全媒体の主要メーター一覧、今日/過去30日の推定コスト、30日トークン合計
  - **媒体別タブ**: 各利用枠のメーターとリセットまでの残り時間、**枯渇予測**（消費ペースから「あと○○で枯渇見込み」を推定）、クレジット消費額、日次トークンの棒グラフ（Claude）
- **設定**: 更新間隔・表示する媒体をトレイメニューから変更（`config.toml` に自動保存）
- **アップデート確認**: GitHub Releases に新版があればメニューに表示

## 対応プロバイダー

| プロバイダー | 方式 | 前提 |
|---|---|---|
| **Claude / Claude Code** | `~/.claude/.credentials.json` の OAuth トークンで `api.anthropic.com/api/oauth/usage` を取得 | Claude Code にログイン済み |
| **OpenAI / Codex** | `~/.codex/auth.json` の OAuth トークンで `chatgpt.com/backend-api/wham/usage` を取得 | Codex CLI にログイン済み |
| **GitHub Copilot** | `gh` CLI のトークンで `api.github.com/copilot_internal/user` を取得（無制限プランはプラン表示のみ） | `gh auth login` 済み |
| **Gemini** | `~/.gemini/oauth_creds.json` で `cloudcode-pa.googleapis.com` を取得 | Gemini CLI 認証済み（下記補足参照） |

未導入・未設定のプロバイダーは自動でスキップされます。

### Gemini の補足

トークンの自動リフレッシュには OAuth クライアント資格情報が必要です。リポジトリには含めていないため、利用する場合は gemini-cli 同梱の値を環境変数に設定してください。

```powershell
$env:CODEXBAR_GEMINI_CLIENT_ID = "<gemini-cli の OAuth クライアント ID>"
$env:CODEXBAR_GEMINI_CLIENT_SECRET = "<同シークレット>"
```

未設定でも既存の `access_token` が有効な間は動作します。プロジェクト ID は自動探索されますが、`GOOGLE_CLOUD_PROJECT` で明示指定も可能です。

## 動作要件

- Windows 10 / 11
- Python 3.11 以上（`tomllib` 標準搭載のため）
- 利用する媒体のツールにログイン済みであること（Claude Code / Codex CLI / gh CLI / Gemini CLI）

## セットアップ

```powershell
git clone https://github.com/ryottaman/codexbar-win.git
cd codexbar-win
pip install -r requirements.txt
```

## 起動

```powershell
# 通常起動（コンソール窓あり・デバッグ用）
python main.py

# コンソール窓なしで常駐
pythonw run.pyw
```

二重起動は自動で抑止されます（2 つ目のプロセスは静かに終了します）。

## 操作

- **アイコンを左クリック** → パネルを開く / 閉じる（`Esc` やクリックアウトでも閉じる）
- **アイコンを右クリック** → メニュー
  - パネルを開く / 今すぐ更新 / 表示するツール / 更新間隔 / claude.ai を開く / アップデート確認 / 終了

## Windows 起動時に自動常駐させる

```powershell
powershell -ExecutionPolicy Bypass -File install_startup.ps1
```

スタートアップフォルダにショートカットを作成します。解除はそのショートカットを削除するだけです。

## 設定（config.toml）

```toml
interval = 300                                      # 更新間隔（秒）
enabled = ["claude", "codex", "copilot", "gemini"]  # 表示するプロバイダー
```

更新間隔・表示するツールはトレイメニューからも変更でき、変更内容は `config.toml` に自動保存されます。

## exe にして配布する（任意）

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

`dist\CodexBar-Win.exe`（単一 exe・Python 不要）が生成されます。exe 実行時の設定・履歴は `%APPDATA%\CodexBar` に保存されます。

## プロバイダーの追加方法

1. `providers/<name>.py` を作り、`fetch() -> UsageResult` を実装する
2. `providers/__init__.py` の `REGISTRY` に登録する

`UsageResult` / `Meter` の型は `providers/base.py` を参照してください。本家 CodexBar には他にも多数の媒体の取得ロジックがあり、同じパターンで移植できます。

## 免責事項

- 本ツールは各 AI 媒体の**公式に文書化されていない内部エンドポイント**を利用します。これらの利用は各社の利用規約で明示的に許可されたものではなく、仕様変更や遮断でいつでも動かなくなる可能性があります。
- 想定用途は**利用者自身が自分の利用状況を確認すること**です。業務上の請求根拠や第三者への提供には使わないでください。
- 認証情報（OAuth トークン等）は**ローカルの既存ファイルを読むだけ**で、外部への送信・保存は行いません。取得先は各媒体の公式ドメインのみです。
- 表示されるコスト・枯渇予測は**概算・推定**であり、実際の請求額や挙動とは一致しません。
- **利用は自己責任でお願いします。** 本ツールの使用に起因するいかなる損害についても作者は責任を負いません。

## ライセンス / 出典

本ツールは [CodexBar](https://github.com/steipete/CodexBar)（MIT License, Copyright © 2026 Peter Steinberger）の設計・取得ロジックを参考に再実装しています。詳細は [ATTRIBUTION.md](./ATTRIBUTION.md) を、ライセンス全文は [LICENSE](./LICENSE) を参照してください。
