"""GitHub Copilot の利用量取得。

方式: GitHub OAuth トークン（gh CLI が保持しているもの）で
api.github.com/copilot_internal/user を叩く。
本家 CodexBar の CopilotUsageFetcher.swift を Python へ移植したもの。

トークンの取得優先順位:
  1. 環境変数 CODEXBAR_GITHUB_TOKEN
  2. gh CLI (`gh auth token`)
プランによっては quota_snapshots が空（無制限）の場合があり、
その場合はメーター無し・プラン情報のみを表示する。
"""
from __future__ import annotations

import os
import shutil
import subprocess

import httpx

from .base import Meter, UsageResult, parse_iso8601

USER_URL = "https://api.github.com/copilot_internal/user"
HEADERS = {
    "Editor-Version": "vscode/1.96.2",
    "Editor-Plugin-Version": "copilot-chat/0.26.7",
    "User-Agent": "GitHubCopilotChat/0.26.7",
    "X-Github-Api-Version": "2025-04-01",
}


def _load_token() -> tuple[str | None, str | None]:
    env = os.environ.get("CODEXBAR_GITHUB_TOKEN")
    if env:
        return env, None
    gh = shutil.which("gh")
    if gh:
        try:
            out = subprocess.run(
                [gh, "auth", "token"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            token = out.stdout.strip()
            if token:
                return token, None
        except (subprocess.SubprocessError, OSError):
            pass
    return None, "GitHub トークンなし（gh CLI 未ログイン）"


def _snapshot_meter(label: str, snap: dict) -> Meter | None:
    if not isinstance(snap, dict):
        return None
    if snap.get("unlimited"):
        return None  # 無制限枠はメーター化しない
    used = snap.get("percent_remaining")
    # percent_remaining があれば used = 100 - remaining、無ければ entitlement/remaining から計算
    try:
        if used is not None:
            used_percent = 100.0 - float(used)
        else:
            ent = snap.get("entitlement")
            rem = snap.get("remaining")
            if ent and rem is not None and float(ent) > 0:
                used_percent = 100.0 * (float(ent) - float(rem)) / float(ent)
            else:
                return None
    except (TypeError, ValueError):
        return None
    return Meter(label=label, used_percent=used_percent)


def fetch(timeout: float = 20.0) -> UsageResult:
    token, err = _load_token()
    if err:
        return UsageResult("Copilot", ok=False, error=err)

    headers = dict(HEADERS)
    headers["Authorization"] = f"token {token}"
    try:
        r = httpx.get(USER_URL, headers=headers, timeout=timeout)
    except httpx.HTTPError as e:
        return UsageResult("Copilot", ok=False, error=f"通信エラー: {e}")

    if r.status_code == 401:
        return UsageResult("Copilot", ok=False, error="認証エラー（Copilot 未契約 or トークン無効）")
    if r.status_code == 403:
        return UsageResult("Copilot", ok=False, error="アクセス権なし（Copilot 未契約）")
    if r.status_code != 200:
        return UsageResult("Copilot", ok=False, error=f"HTTP {r.status_code}")

    try:
        data = r.json()
    except ValueError:
        return UsageResult("Copilot", ok=False, error="レスポンス解析エラー")

    meters: list[Meter] = []
    snapshots = data.get("quota_snapshots") or {}
    if isinstance(snapshots, dict):
        for key, label in (
            ("premium_interactions", "Premium"),
            ("chat", "Chat"),
            ("completions", "補完"),
        ):
            m = _snapshot_meter(label, snapshots.get(key))
            if m is not None:
                reset = parse_iso8601(data.get("quota_reset_date"))
                if reset:
                    m.resets_at = reset
                meters.append(m)

    extra: dict = {}
    notes: list[str] = []
    plan = data.get("copilot_plan")
    if plan:
        extra["plan_type"] = plan
    if not meters:
        # 上限管理のないプラン。プラン情報だけ出す。
        notes.append(f"プラン: {plan or '不明'}（上限データなし/無制限）")
        return UsageResult("Copilot", ok=True, meters=[], extra=extra, notes=notes)

    if data.get("quota_reset_date"):
        notes.append(f"リセット日: {data['quota_reset_date']}")
    return UsageResult("Copilot", ok=True, meters=meters, extra=extra, notes=notes)
