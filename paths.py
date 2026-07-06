"""設定・履歴などローカル状態の保存先を決める。

- 通常実行: スクリプトのあるフォルダ
- exe 化（PyInstaller onefile）: %APPDATA%\\CodexBar
  exe の隣は Program Files 等の書込不可の場所になり得るため使わない。
"""
from __future__ import annotations

import os
import sys


def _resolve() -> str:
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("APPDATA")
        if appdata:
            d = os.path.join(appdata, "CodexBar")
            try:
                os.makedirs(d, exist_ok=True)
                return d
            except OSError:
                pass
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


APP_DIR = _resolve()
