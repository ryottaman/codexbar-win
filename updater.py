"""GitHub Releases を見て新しいバージョンがあるか確認する。

自動でバイナリを差し替える本格的なオートアップデートではなく、
「新しい版が出たら知らせてリリースページを開く」軽量方式。
Python 製常駐アプリではこれが最も無理がない。
"""
from __future__ import annotations

import re

import httpx

from version import GITHUB_REPO, __version__

RELEASES_API = "https://api.github.com/repos/{repo}/releases/latest"
RELEASES_PAGE = "https://github.com/{repo}/releases/latest"


def _parse(v: str) -> tuple:
    """バージョン文字列を比較用タプルに変換する。桁数を揃えて 0.1 と 0.1.0 を同値に扱う。"""
    nums = [int(n) for n in re.findall(r"\d+", v or "")][:4]
    return tuple(nums + [0] * (4 - len(nums)))


def check() -> dict | None:
    """新版があれば {"latest","url","current"} を返す。無ければ/失敗時は None。"""
    if not GITHUB_REPO or "/" not in GITHUB_REPO:
        return None
    try:
        r = httpx.get(
            RELEASES_API.format(repo=GITHUB_REPO),
            headers={"Accept": "application/vnd.github+json", "User-Agent": "codexbar-win"},
            timeout=10,
            follow_redirects=True,
        )
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None  # 未公開・リリースなし・404 など
    try:
        data = r.json()
    except ValueError:
        return None
    tag = data.get("tag_name", "")
    if not tag:
        return None
    if _parse(tag) > _parse(__version__):
        return {
            "latest": tag,
            "current": __version__,
            "url": data.get("html_url") or RELEASES_PAGE.format(repo=GITHUB_REPO),
        }
    return None
