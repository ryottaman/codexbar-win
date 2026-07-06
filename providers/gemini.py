"""Gemini (Gemini CLI / Code Assist) の利用量取得。

方式: Gemini CLI が保存した OAuth 資格情報（~/.gemini/oauth_creds.json）で
Google の内部 Cloud Code API を叩く。
本家 CodexBar の GeminiStatusProbe.swift を Python へ移植したもの。

アクセストークンが期限切れの場合は oauth2.googleapis.com/token でリフレッシュする。
Gemini CLI 未認証（oauth_creds.json 無し）の環境では ok=False（未導入）で自動スキップ。
"""
from __future__ import annotations

import json
import os
import time

import httpx

from .base import Meter, UsageResult, parse_iso8601

GEMINI_DIR = os.path.expanduser("~/.gemini")
CREDS_PATH = os.path.join(GEMINI_DIR, "oauth_creds.json")

QUOTA_URL = "https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuota"
LOAD_URL = "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist"
PROJECTS_URL = "https://cloudresourcemanager.googleapis.com/v1/projects"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# gemini-cli 同梱の OAuth クライアント（Code Assist 用）。
# Google のクライアント資格情報はリポジトリに含めず、環境変数から読む。
# 未設定の場合はトークンのリフレッシュを行わず、既存の access_token をそのまま使う。
# gemini-cli をインストール済みなら、その OAuth クライアント値を環境変数に設定すること。
CLIENT_ID = os.environ.get("CODEXBAR_GEMINI_CLIENT_ID")
CLIENT_SECRET = os.environ.get("CODEXBAR_GEMINI_CLIENT_SECRET")


def _load_creds() -> tuple[dict | None, str | None]:
    if not os.path.exists(CREDS_PATH):
        return None, "Gemini CLI 未認証"
    try:
        with open(CREDS_PATH, encoding="utf-8") as f:
            return json.load(f), None
    except (OSError, json.JSONDecodeError) as e:
        return None, f"oauth_creds.json 読取エラー: {e}"


def _refresh(refresh_token: str, timeout: float) -> str | None:
    if not CLIENT_ID or not CLIENT_SECRET:
        return None  # クライアント資格情報が無いのでリフレッシュ不可
    try:
        r = httpx.post(
            TOKEN_URL,
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=timeout,
        )
        if r.status_code == 200:
            return r.json().get("access_token")
    except httpx.HTTPError:
        pass
    return None


def _access_token(creds: dict, timeout: float) -> str | None:
    token = creds.get("access_token")
    expiry = creds.get("expiry_date")  # ミリ秒 or None
    valid = token and (not expiry or expiry / 1000 > time.time() + 60)
    if valid:
        return token
    rt = creds.get("refresh_token")
    if rt:
        return _refresh(rt, timeout)
    return token


def _find_project(token: str, timeout: float) -> str | None:
    try:
        r = httpx.get(
            PROJECTS_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
        if r.status_code == 200:
            projects = r.json().get("projects", [])
            for p in projects:
                if p.get("lifecycleState") == "ACTIVE":
                    return p.get("projectId")
    except httpx.HTTPError:
        pass
    return None


def fetch(timeout: float = 20.0) -> UsageResult:
    creds, err = _load_creds()
    if err:
        return UsageResult("Gemini", ok=False, error=err)

    token = _access_token(creds, timeout)
    if not token:
        return UsageResult("Gemini", ok=False, error="トークン取得失敗（再ログインが必要）")

    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or _find_project(token, timeout)
    body = {"project": project} if project else {}

    try:
        r = httpx.post(
            QUOTA_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=timeout,
        )
    except httpx.HTTPError as e:
        return UsageResult("Gemini", ok=False, error=f"通信エラー: {e}")

    if r.status_code == 401:
        return UsageResult("Gemini", ok=False, error="認証エラー（再ログインが必要）")
    if r.status_code != 200:
        return UsageResult("Gemini", ok=False, error=f"HTTP {r.status_code}")

    try:
        data = r.json()
    except ValueError:
        return UsageResult("Gemini", ok=False, error="レスポンス解析エラー")

    meters: list[Meter] = []
    # レスポンス構造は quotas / userQuota など環境で異なるため両対応
    quotas = data.get("quotas") or data.get("userQuota") or []
    if isinstance(quotas, dict):
        quotas = [quotas]
    for q in quotas:
        if not isinstance(q, dict):
            continue
        left = q.get("percentLeft")
        if left is None:
            continue
        name = q.get("quotaId") or q.get("name") or "quota"
        meters.append(
            Meter(
                label=str(name),
                used_percent=100.0 - float(left),
                resets_at=parse_iso8601(q.get("resetTime")),
            )
        )

    if not meters:
        return UsageResult("Gemini", ok=True, meters=[], notes=["クォータ情報なし（無制限 or 未対応プラン）"])
    return UsageResult("Gemini", ok=True, meters=meters)
