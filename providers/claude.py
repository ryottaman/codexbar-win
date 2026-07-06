"""Claude / Claude Code の利用量取得。

方式: Claude Code が保存した OAuth トークン（~/.claude/.credentials.json）を
公式の内部 usage エンドポイントに付けて GET する。
本家 CodexBar の ClaudeOAuthUsageFetcher.swift を Python へ移植したもの。
"""
from __future__ import annotations

import json
import os
import time

import httpx

from .base import Meter, UsageResult, parse_iso8601

CREDENTIALS_PATH = os.path.expanduser("~/.claude/.credentials.json")
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"

# 表示したい枠のラベル対応表（存在するものだけ表示）
WINDOW_LABELS = {
    "five_hour": "5時間",
    "seven_day": "7日",
    "seven_day_opus": "7日 Opus",
    "seven_day_sonnet": "7日 Sonnet",
}


def _load_token() -> tuple[str | None, str | None]:
    """(access_token, error) を返す。"""
    # 環境変数による上書き（テスト用）
    env = os.environ.get("CODEXBAR_CLAUDE_OAUTH_TOKEN")
    if env:
        return env, None
    if not os.path.exists(CREDENTIALS_PATH):
        return None, "認証ファイルが見つかりません（Claude Code 未ログイン）"
    try:
        with open(CREDENTIALS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return None, f"認証ファイル読取エラー: {e}"
    oauth = data.get("claudeAiOauth") or {}
    token = oauth.get("accessToken")
    if not token:
        return None, "accessToken が見つかりません"
    expires_at = oauth.get("expiresAt", 0)  # ミリ秒
    if expires_at and expires_at / 1000 < time.time():
        return None, "トークン期限切れ（Claude Code で再ログインが必要）"
    return token, None


def fetch(timeout: float = 20.0) -> UsageResult:
    token, err = _load_token()
    if err:
        return UsageResult("Claude", ok=False, error=err)

    try:
        r = httpx.get(
            USAGE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "anthropic-beta": "oauth-2025-04-20",
                "User-Agent": "claude-code/2.1.0",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
    except httpx.HTTPError as e:
        return UsageResult("Claude", ok=False, error=f"通信エラー: {e}")

    if r.status_code == 401:
        return UsageResult("Claude", ok=False, error="認証エラー（再ログインが必要）")
    if r.status_code == 429:
        retry = r.headers.get("Retry-After", "?")
        return UsageResult("Claude", ok=False, error=f"レート制限（{retry}秒後）")
    if r.status_code != 200:
        return UsageResult("Claude", ok=False, error=f"HTTP {r.status_code}")

    try:
        data = r.json()
    except ValueError:
        return UsageResult("Claude", ok=False, error="レスポンス解析エラー")

    meters: list[Meter] = []
    for key, label in WINDOW_LABELS.items():
        win = data.get(key)
        if isinstance(win, dict) and win.get("utilization") is not None:
            try:
                pct = float(win["utilization"])
            except (TypeError, ValueError):
                continue  # 1 枠の異常値で他の枠まで消さない
            meters.append(
                Meter(
                    label=label,
                    used_percent=pct,
                    resets_at=parse_iso8601(win.get("resets_at")),
                )
            )

    extra: dict = {}
    eu = data.get("extra_usage")
    if isinstance(eu, dict) and eu.get("is_enabled"):
        extra["extra_usage"] = {
            "used_credits": eu.get("used_credits"),
            "monthly_limit": eu.get("monthly_limit"),
            "utilization": eu.get("utilization"),
            "currency": eu.get("currency"),
        }

    # クレジット消費額（spend）。Admin API 不要で OAuth レスポンスに含まれる。
    spend = data.get("spend")
    if isinstance(spend, dict):
        used = spend.get("used") or {}
        limit = spend.get("limit") or {}
        exp = used.get("exponent", 2)
        extra["spend"] = {
            "used": (used.get("amount_minor", 0) or 0) / (10 ** exp),
            "limit": (limit.get("amount_minor", 0) or 0) / (10 ** (limit.get("exponent", 2))),
            "currency": used.get("currency", "USD"),
            "percent": spend.get("percent"),
        }

    # モデル名付きの詳細枠（アクティブなもの）
    detail = []
    for lim in data.get("limits", []) or []:
        if not isinstance(lim, dict) or lim.get("percent") is None:
            continue
        scope = lim.get("scope") or {}
        model = (scope.get("model") or {}).get("display_name") if isinstance(scope, dict) else None
        detail.append(
            {
                "kind": lim.get("kind"),
                "percent": lim.get("percent"),
                "model": model,
                "severity": lim.get("severity"),
                "is_active": lim.get("is_active"),
            }
        )
    if detail:
        extra["limits_detail"] = detail

    if not meters:
        return UsageResult("Claude", ok=False, error="利用枠データなし")
    return UsageResult("Claude", ok=True, meters=meters, extra=extra)
