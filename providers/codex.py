"""OpenAI / Codex CLI の利用量取得。

方式: Codex CLI が保存した OAuth トークン（~/.codex/auth.json）を
chatgpt.com の内部 usage エンドポイントに付けて GET する。
本家 CodexBar の CodexOAuthUsageFetcher.swift を Python へ移植したもの。

Codex CLI を導入していない環境では auth.json が無いため、
fetch() は ok=False（未導入）を返し、UI 側でスキップされる。
"""
from __future__ import annotations

import json
import os

import httpx

from .base import Meter, UsageResult

CODEX_HOME = os.environ.get("CODEX_HOME", os.path.expanduser("~/.codex"))
AUTH_PATH = os.path.join(CODEX_HOME, "auth.json")
USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"


def _load_auth() -> tuple[dict | None, str | None]:
    if not os.path.exists(AUTH_PATH):
        return None, "Codex CLI 未導入"
    try:
        with open(AUTH_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return None, f"auth.json 読取エラー: {e}"
    tokens = data.get("tokens") or {}
    if not tokens.get("access_token"):
        return None, "access_token が見つかりません"
    return tokens, None


def fetch(timeout: float = 20.0) -> UsageResult:
    tokens, err = _load_auth()
    if err:
        return UsageResult("Codex", ok=False, error=err)

    headers = {
        "Authorization": f"Bearer {tokens['access_token']}",
        "User-Agent": "CodexBar",
    }
    if tokens.get("account_id"):
        headers["ChatGPT-Account-Id"] = tokens["account_id"]

    try:
        r = httpx.get(USAGE_URL, headers=headers, timeout=timeout)
    except httpx.HTTPError as e:
        return UsageResult("Codex", ok=False, error=f"通信エラー: {e}")

    if r.status_code == 401:
        return UsageResult("Codex", ok=False, error="認証エラー（再ログインが必要）")
    if r.status_code != 200:
        return UsageResult("Codex", ok=False, error=f"HTTP {r.status_code}")

    try:
        data = r.json()
    except ValueError:
        return UsageResult("Codex", ok=False, error="レスポンス解析エラー")

    meters: list[Meter] = []
    rate = data.get("rate_limit") or {}
    for key, label in (("primary_window", "主枠"), ("secondary_window", "副枠")):
        win = rate.get(key)
        if isinstance(win, dict) and win.get("used_percent") is not None:
            resets_at = None
            reset_epoch = win.get("reset_at")
            if reset_epoch:
                from datetime import datetime, timezone

                resets_at = datetime.fromtimestamp(int(reset_epoch), tz=timezone.utc)
            meters.append(
                Meter(
                    label=label,
                    used_percent=float(win["used_percent"]),
                    resets_at=resets_at,
                )
            )

    extra: dict = {}
    if data.get("plan_type"):
        extra["plan_type"] = data["plan_type"]
    credits = data.get("credits")
    if isinstance(credits, dict) and credits.get("has_credits"):
        extra["credits_balance"] = credits.get("balance")

    if not meters:
        return UsageResult("Codex", ok=False, error="利用枠データなし")
    return UsageResult("Codex", ok=True, meters=meters, extra=extra)
