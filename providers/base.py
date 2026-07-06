"""プロバイダー共通の型定義。

各プロバイダーは fetch() を実装し、UsageResult を返す。
UI 層はこの正規化された型だけを見るので、媒体ごとの差異はここで吸収する。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Meter:
    """1 つの利用枠（例: 5時間窓、7日窓）。"""

    label: str
    used_percent: float
    resets_at: datetime | None = None

    def reset_in_text(self) -> str:
        """リセットまでの残り時間を人間可読な文字列で返す。"""
        if self.resets_at is None:
            return ""
        delta = self.resets_at - datetime.now(timezone.utc)
        secs = int(delta.total_seconds())
        if secs <= 0:
            return "まもなくリセット"
        days, rem = divmod(secs, 86400)
        hours, rem = divmod(rem, 3600)
        mins = rem // 60
        if days > 0:
            return f"あと{days}日{hours}時間"
        if hours > 0:
            return f"あと{hours}時間{mins}分"
        return f"あと{mins}分"


@dataclass
class UsageResult:
    """1 プロバイダーの取得結果。"""

    provider: str
    ok: bool
    meters: list[Meter] = field(default_factory=list)
    error: str | None = None
    # 従量課金などの補足情報（任意）
    extra: dict = field(default_factory=dict)
    # メーターは無いが表示したい情報行（例: 無制限プラン、残クレジット）
    notes: list[str] = field(default_factory=list)

    @property
    def max_percent(self) -> float:
        """アクティブな枠の中で最も逼迫している使用率。"""
        if not self.meters:
            return 0.0
        return max(m.used_percent for m in self.meters)


def parse_iso8601(value: str | None) -> datetime | None:
    """ISO8601 文字列を timezone-aware な datetime に変換する。"""
    if not value:
        return None
    try:
        # Python の fromisoformat は末尾 Z を扱えないので置換
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
