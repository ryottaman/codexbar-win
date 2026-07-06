"""USD→JPY 為替レートの取得。

open.er-api.com（無料・キー不要）から取得し、12時間キャッシュする。
取得失敗時は最後に成功した値、それも無ければフォールバック値を使う。
config.toml の usd_jpy で固定レートに上書きできる。
"""
from __future__ import annotations

import time

import httpx

FALLBACK_RATE = 150.0
RATE_URL = "https://open.er-api.com/v6/latest/USD"
TTL_SEC = 12 * 3600

_cache: dict = {"rate": None, "at": 0.0}


def get_rate(timeout: float = 10.0) -> float:
    """現在の USD/JPY レートを返す（キャッシュ付き・失敗時フォールバック）。"""
    now = time.time()
    if _cache["rate"] and now - _cache["at"] < TTL_SEC:
        return _cache["rate"]
    try:
        r = httpx.get(RATE_URL, timeout=timeout)
        if r.status_code == 200:
            rate = (r.json().get("rates") or {}).get("JPY")
            if rate:
                _cache["rate"] = float(rate)
                _cache["at"] = now
                return _cache["rate"]
    except (httpx.HTTPError, ValueError):
        pass
    return _cache["rate"] or FALLBACK_RATE
