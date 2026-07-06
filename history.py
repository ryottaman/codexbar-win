"""利用率の履歴を蓄積し、消費ペースから枯渇時刻を予測する。

各リフレッシュ時に (時刻, 使用率) をメーターごとに記録し、直近の単調増加区間
（＝前回リセット以降）の傾きから「あと何分で 100%」を推定する。
本家 CodexBar の「○分後に枯渇する見込み」に相当。追加依存なし。
"""
from __future__ import annotations

import json
import os
import sys
import time

if getattr(sys, "frozen", False):
    _BASE = os.path.dirname(sys.executable)
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))
HISTORY_PATH = os.path.join(_BASE, "usage_history.json")
MAX_POINTS = 60          # メーターごとの保持点数
LOOKBACK_SEC = 24 * 3600  # 予測に使う最長遡り時間


def _load() -> dict:
    if not os.path.exists(HISTORY_PATH):
        return {}
    try:
        with open(HISTORY_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    try:
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


def record(results) -> None:
    """現在の各メーターの使用率を履歴に追記する。"""
    data = _load()
    now = time.time()
    for r in results:
        if not getattr(r, "ok", False):
            continue
        for m in r.meters:
            key = f"{r.provider}:{m.label}"
            series = data.get(key, [])
            series.append([round(now, 1), round(float(m.used_percent), 2)])
            if len(series) > MAX_POINTS:
                series = series[-MAX_POINTS:]
            data[key] = series
    _save(data)


def eta_minutes(provider: str, label: str, current_percent: float) -> float | None:
    """当該メーターが 100% に到達するまでの推定分数。予測不能なら None。"""
    data = _load()
    key = f"{provider}:{label}"
    series = data.get(key)
    if not series or len(series) < 2:
        return None

    now = time.time()
    # 直近の点から過去へ、単調増加（過去ほど小さい）を保つ範囲を遡る。
    # リセットで値が下がった箇所は超えない＝現在の窓の起点を見つける。
    pts = [(t, v) for t, v in series if now - t <= LOOKBACK_SEC]
    if len(pts) < 2:
        return None
    cur_t, cur_v = pts[-1]
    base_t, base_v = cur_t, cur_v
    for t, v in reversed(pts[:-1]):
        if v <= base_v:  # 過去に向かって値が小さい＝同じ窓の中
            base_t, base_v = t, v
        else:
            break  # リセット跨ぎ。ここで打ち切り

    dt_min = (cur_t - base_t) / 60.0
    dv = cur_v - base_v
    if dt_min < 1 or dv <= 0:
        return None
    rate = dv / dt_min  # %/分
    remaining = 100.0 - cur_v
    if remaining <= 0:
        return 0.0
    return remaining / rate


def eta_text(provider: str, label: str, current_percent: float) -> str | None:
    """「あと○○で枯渇見込み」の文字列。予測不能なら None。"""
    eta = eta_minutes(provider, label, current_percent)
    if eta is None:
        return None
    mins = int(round(eta))
    if mins <= 0:
        return "まもなく枯渇見込み"
    if mins >= 1440:
        days = mins // 1440
        hours = (mins % 1440) // 60
        return f"あと{days}日{hours}時間で枯渇見込み"
    if mins >= 60:
        return f"あと{mins // 60}時間{mins % 60}分で枯渇見込み"
    return f"あと{mins}分で枯渇見込み"
