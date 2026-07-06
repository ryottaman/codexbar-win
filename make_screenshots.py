"""README 用スクリーンショット（docs/panel-*.png）をデモデータで生成する。

PrintWindow API で対象ウィンドウの中身だけをキャプチャするため、
他のウィンドウに隠れていても正しく撮れる。実利用の数値は使わない。

使い方: python make_screenshots.py
"""
from __future__ import annotations

import ctypes
import sys
import time
import tkinter as tk
from datetime import datetime, timedelta, timezone

from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

import panel as panel_mod
from providers.base import Meter, UsageResult
from usage_stats import DailyStats

GA_ROOT = 2
PW_RENDERFULLCONTENT = 2


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


def capture(win: tk.Toplevel) -> Image.Image:
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    hwnd = user32.GetAncestor(win.winfo_id(), GA_ROOT)
    w, h = win.winfo_width(), win.winfo_height()
    hdc_win = user32.GetWindowDC(hwnd)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_win)
    bmp = gdi32.CreateCompatibleBitmap(hdc_win, w, h)
    gdi32.SelectObject(hdc_mem, bmp)
    user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)
    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth, bmi.biHeight = w, -h
    bmi.biPlanes, bmi.biBitCount = 1, 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(hdc_mem, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(hwnd, hdc_win)
    return img.convert("RGB")


def demo_data():
    now = datetime.now(timezone.utc)
    claude = UsageResult(
        "Claude", ok=True,
        meters=[
            Meter("5時間", 34.0, now + timedelta(hours=2, minutes=10)),
            Meter("7日", 61.0, now + timedelta(days=2, hours=5)),
            Meter("7日 Opus", 48.0, now + timedelta(days=2, hours=5)),
        ],
        extra={"spend": {"used": 12.40, "limit": 50.0, "currency": "USD", "percent": 25}},
    )
    codex = UsageResult(
        "Codex", ok=True,
        meters=[
            Meter("主枠", 22.0, now + timedelta(hours=3)),
            Meter("副枠", 74.0, now + timedelta(days=4)),
        ],
        extra={"plan_type": "plus"},
    )
    copilot = UsageResult("Copilot", ok=True, meters=[], notes=["プラン: individual（上限データなし/無制限）"], extra={"plan_type": "individual"})
    gemini = UsageResult("Gemini", ok=False, error="Gemini CLI 未認証")

    stats = DailyStats()
    today = datetime.now().astimezone().date()
    import math
    for i in range(14):
        d = (today - timedelta(days=13 - i)).isoformat()
        tok = int(40_000_000 + 30_000_000 * math.sin(i / 2.2) ** 2 + i * 4_000_000)
        stats.by_day[d] = {"tokens": tok, "cost": tok / 1_000_000 * 2.4}
    stats.today_tokens = stats.by_day[today.isoformat()]["tokens"]
    stats.today_cost = stats.by_day[today.isoformat()]["cost"]
    stats.total_tokens = sum(e["tokens"] for e in stats.by_day.values())
    stats.total_cost = sum(e["cost"] for e in stats.by_day.values())
    stats.computed_at = time.time()
    return [claude, codex, copilot, gemini], stats


def main():
    results, stats = demo_data()
    root = tk.Tk()
    root.withdraw()
    p = panel_mod.Panel(root)

    for tab, path in (("概要", "docs/panel-overview.png"), ("Claude", "docs/panel-claude.png")):
        p.active_tab = tab
        p.show(results, stats, steal_focus=False, fx_rate=155.0)  # デモ用固定レート
        w = p.win
        w.geometry("+50+50")
        for _ in range(30):
            root.update()
            root.update_idletasks()
            time.sleep(0.03)
        img = capture(w)
        img.save(path)
        print(f"saved {path} ({img.size[0]}x{img.size[1]})")
        p.hide()
    root.destroy()


if __name__ == "__main__":
    main()
