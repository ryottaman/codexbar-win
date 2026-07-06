"""Claude Code のローカルログ（~/.claude/projects/**/*.jsonl）から
日次のトークン使用量と推定コストを集計する。

本家 CodexBar の「ローカルログから推定」に相当。各アシスタントメッセージの
usage（input/output/cache トークン）をモデル別価格で金額換算する。
価格は概算であり、表示は「推定」として扱う。
"""
from __future__ import annotations

import glob
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta

PROJECTS_DIR = os.path.expanduser("~/.claude/projects")

# モデル別価格（USD / 100万トークン）。部分一致で判定。
# input, output, cache_read, cache_write の順。
# cache_read = input の 0.1 倍、cache_write = input の 1.25 倍（5分TTL）。
# 出典: Claude API 公式価格（2026-05 時点）。変更され得るため概算として扱う。
PRICING = {
    "fable": (10.0, 50.0, 1.0, 12.5),   # Fable 5
    "opus": (5.0, 25.0, 0.5, 6.25),     # Opus 4.5 以降
    "sonnet": (3.0, 15.0, 0.30, 3.75),  # Sonnet 4.x
    "haiku": (1.0, 5.0, 0.10, 1.25),    # Haiku 4.5
}
DEFAULT_PRICE = (3.0, 15.0, 0.30, 3.75)  # 不明モデルは Sonnet 相当


def _price_for(model: str | None):
    if not model:
        return DEFAULT_PRICE
    m = model.lower()
    for key, price in PRICING.items():
        if key in m:
            return price
    return DEFAULT_PRICE


def _cost(usage: dict, model: str | None) -> float:
    pin, pout, pcache_r, pcache_w = _price_for(model)
    it = usage.get("input_tokens", 0) or 0
    ot = usage.get("output_tokens", 0) or 0
    cr = usage.get("cache_read_input_tokens", 0) or 0
    cw = usage.get("cache_creation_input_tokens", 0) or 0
    return (it * pin + ot * pout + cr * pcache_r + cw * pcache_w) / 1_000_000


class DailyStats:
    def __init__(self):
        self.by_day: dict[str, dict] = {}  # "YYYY-MM-DD" -> {tokens, cost}
        self.total_tokens = 0
        self.total_cost = 0.0
        self.today_cost = 0.0
        self.today_tokens = 0
        self.computed_at = 0.0

    def daily_series(self, days: int = 14) -> list[tuple[str, int, float]]:
        """直近 days 日の (日付, トークン, コスト) を古い順で返す（欠損日は0）。"""
        today = datetime.now().astimezone().date()
        out = []
        for i in range(days - 1, -1, -1):
            d = (today - timedelta(days=i)).isoformat()
            e = self.by_day.get(d, {})
            out.append((d, e.get("tokens", 0), e.get("cost", 0.0)))
        return out


def _day_local(ts: str, offset_min: int) -> str | None:
    """ISO8601 の UTC タイムスタンプをローカル日（YYYY-MM-DD）に変換する。

    ログは行数が多いため、固定書式（YYYY-MM-DDTHH:MM...Z）前提の
    文字列スライスで高速に処理し、想定外の書式のみ fromisoformat に落とす。
    """
    try:
        y, mo, d = int(ts[0:4]), int(ts[5:7]), int(ts[8:10])
        minutes = int(ts[11:13]) * 60 + int(ts[14:16]) + offset_min
        day = datetime(y, mo, d).date()
        if minutes >= 1440:
            day += timedelta(days=1)
        elif minutes < 0:
            day -= timedelta(days=1)
        return day.isoformat()
    except (ValueError, IndexError):
        pass
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone().date().isoformat()


def compute(days: int = 30) -> DailyStats:
    """直近 days 日分を集計する。更新のあったファイルのみ読む。

    「今日」「日次」はローカル日（JST 等）基準。UTC 基準だと 09:00 JST を境に
    「今日」がリセットされ体感とずれるため、ローカル日に揃えている。
    """
    stats = DailyStats()
    stats.computed_at = time.time()
    if not os.path.isdir(PROJECTS_DIR):
        return stats

    cutoff = time.time() - (days + 1) * 86400
    now_local = datetime.now().astimezone()
    offset_min = int((now_local.utcoffset() or timedelta()).total_seconds() // 60)
    today_date = now_local.date()
    today = today_date.isoformat()
    min_day = (today_date - timedelta(days=days - 1)).isoformat()
    agg = defaultdict(lambda: {"tokens": 0, "cost": 0.0})

    for path in glob.glob(os.path.join(PROJECTS_DIR, "**", "*.jsonl"), recursive=True):
        try:
            if os.path.getmtime(path) < cutoff:
                continue
        except OSError:
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    if '"usage"' not in line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    msg = obj.get("message")
                    if not isinstance(msg, dict):
                        continue
                    usage = msg.get("usage")
                    ts = obj.get("timestamp")
                    if not isinstance(usage, dict) or not isinstance(ts, str):
                        continue
                    day = _day_local(ts, offset_min)
                    if day is None or day < min_day or day > today:
                        continue  # 集計範囲外（古いファイル内の残存行など）
                    tokens = (
                        (usage.get("input_tokens", 0) or 0)
                        + (usage.get("output_tokens", 0) or 0)
                        + (usage.get("cache_read_input_tokens", 0) or 0)
                        + (usage.get("cache_creation_input_tokens", 0) or 0)
                    )
                    agg[day]["tokens"] += tokens
                    agg[day]["cost"] += _cost(usage, msg.get("model"))
        except OSError:
            continue

    stats.by_day = dict(agg)
    for day, e in agg.items():
        stats.total_tokens += e["tokens"]
        stats.total_cost += e["cost"]
    t = agg.get(today, {})
    stats.today_tokens = t.get("tokens", 0)
    stats.today_cost = t.get("cost", 0.0)
    return stats


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)
