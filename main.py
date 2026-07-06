"""CodexBar for Windows — AI コーディングツールの利用量をタスクトレイに常駐表示する。

本家 CodexBar (macOS, by steipete, MIT License) の中核ロジックを
Windows/Python 向けに再実装したもの。取得ロジックは各 providers/*.py を参照。

構成:
- Tk メインループ（メインスレッド）… クリックで開くパネル UI
- pystray アイコン（run_detached）… タスクトレイ常駐
- ポーリングスレッド（daemon）… 定期的に各媒体を取得
UI 操作はキュー経由で Tk スレッドへ整流している。

使い方:
    python main.py       # デバッグ（コンソール窓あり）
    pythonw run.pyw      # 常駐（コンソール窓なし）
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import time
import tkinter as tk
import tomllib
import webbrowser

import pystray
from pystray import Menu, MenuItem

import history
import iconutil
import panel as panel_mod
import updater
import usage_stats
from providers import REGISTRY
from providers.base import UsageResult
from version import __version__

# pythonw.exe 起動時は stdout/stderr が None になる。
# print() でのクラッシュを防ぐため devnull に差し替え、コンソールがあれば UTF-8 に。
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
else:
    sys.stdout.reconfigure(encoding="utf-8")

from paths import APP_DIR

CONFIG_PATH = os.path.join(APP_DIR, "config.toml")
DEFAULT_INTERVAL = 300  # 秒
INTERVAL_PRESETS = [(60, "1分"), (300, "5分"), (900, "15分"), (1800, "30分")]
PROVIDER_KEYS = [key for key, _name, _fetch in REGISTRY]
PROVIDER_NAMES = {key: name for key, name, _fetch in REGISTRY}

_ERROR_ALREADY_EXISTS = 183
_mutex_handle = None  # プロセス生存中はミューテックスを保持し続ける


def acquire_single_instance() -> bool:
    """名前付きミューテックスで二重起動を防ぐ。2つ目のプロセスなら False。"""
    global _mutex_handle
    import ctypes

    _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, "codexbar-win-instance")
    return ctypes.windll.kernel32.GetLastError() != _ERROR_ALREADY_EXISTS


class Config:
    """config.toml の読み書き。tomllib は読取専用なので書込は自前で行う。"""

    def __init__(self) -> None:
        self.interval = DEFAULT_INTERVAL
        self.enabled = {k: True for k in PROVIDER_KEYS}
        self.load()

    def load(self) -> None:
        if not os.path.exists(CONFIG_PATH):
            return
        try:
            with open(CONFIG_PATH, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            print(f"config.toml 読取エラー（デフォルト使用）: {e}")
            return
        self.interval = int(data.get("interval", DEFAULT_INTERVAL))
        enabled = data.get("enabled")
        if isinstance(enabled, list):
            self.enabled = {k: (k in enabled) for k in PROVIDER_KEYS}

    def save(self) -> None:
        lines = [
            "# CodexBar for Windows 設定",
            "# トレイメニューから変更するとこのファイルが自動更新される。",
            "",
            f"interval = {self.interval}",
            "",
            "# 表示するプロバイダー。",
            '# 選択肢: "claude", "codex", "copilot", "gemini"',
            "enabled = [" + ", ".join(f'"{k}"' for k in PROVIDER_KEYS if self.enabled.get(k)) + "]",
            "",
        ]
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except OSError as e:
            print(f"config.toml 保存エラー: {e}")


class CodexBarApp:
    def __init__(self) -> None:
        self.config = Config()
        self.results: list[UsageResult] = []
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self.ui_q: queue.Queue = queue.Queue()
        self.stats: usage_stats.DailyStats | None = None
        self._stats_computing = False
        self._stats_lock = threading.Lock()
        self._update_info: dict | None = None

        # Tk（メインスレッド）。ルートは隠しておき、パネルだけ表示する。
        self.root = tk.Tk()
        self.root.withdraw()
        self.panel = panel_mod.Panel(self.root)

        self.icon = pystray.Icon(
            "codexbar-win",
            icon=iconutil.make_icon(0),
            title="CodexBar (起動中…)",
            menu=self._build_menu(),
        )

    # ---- データ取得 ----
    def _active_providers(self):
        for key, name, fetch in REGISTRY:
            if self.config.enabled.get(key, True):
                yield key, name, fetch

    def refresh(self) -> None:
        results: list[UsageResult] = []
        for _key, name, fetch in self._active_providers():
            try:
                results.append(fetch())
            except Exception as e:
                results.append(UsageResult(name, ok=False, error=f"予期しないエラー: {e}"))
        with self.lock:
            self.results = results
        try:
            history.record(results)      # 枯渇予測用に使用率を記録
        except Exception as e:
            print(f"履歴記録エラー: {e}")
        self._apply_icon()
        self.ui_q.put(("data",))         # パネルが開いていれば更新
        self._maybe_compute_stats()      # コスト/トークン集計（重いので別スレッド）

    def _maybe_compute_stats(self, force: bool = False) -> None:
        """Claude Code ログ集計をバックグラウンドで実行しキャッシュする。"""
        with self._stats_lock:
            if self._stats_computing:
                return
            recent = self.stats and (time.time() - self.stats.computed_at < 600)
            if recent and not force:
                return
            self._stats_computing = True

        def work():
            try:
                s = usage_stats.compute(30)
                self.stats = s
                self.ui_q.put(("data",))
            except Exception as e:
                print(f"stats 集計エラー: {e}")
            finally:
                self._stats_computing = False

        threading.Thread(target=work, daemon=True).start()

    def _apply_icon(self) -> None:
        with self.lock:
            results = list(self.results)
        metered = [r for r in results if r.ok and r.meters]
        if metered:
            self.icon.icon = iconutil.make_icon(max(r.max_percent for r in metered))
        elif any(r.ok for r in results):
            self.icon.icon = iconutil.make_icon(0)
        else:
            self.icon.icon = iconutil.make_icon(None, error=True)

        parts = []
        for r in results:
            if r.ok and r.meters:
                parts.append(f"{r.provider} {int(round(r.max_percent))}%")
            elif r.ok:
                parts.append(f"{r.provider} ✓")
            else:
                parts.append(f"{r.provider} ✕")
        self.icon.title = "CodexBar  " + "  |  ".join(parts) if parts else "CodexBar"

    # ---- トレイメニュー（右クリック） ----
    def _build_menu(self) -> Menu:
        return Menu(
            MenuItem("パネルを開く", self._menu_toggle_panel, default=True),
            MenuItem("今すぐ更新", lambda: self._on_refresh()),
            MenuItem("表示するツール", self._providers_submenu()),
            MenuItem("更新間隔", self._interval_submenu()),
            MenuItem("claude.ai を開く", lambda: webbrowser.open("https://claude.ai/settings/usage")),
            Menu.SEPARATOR,
            MenuItem(self._update_label(), self._menu_check_update),
            MenuItem("終了", self._menu_quit),
        )

    def _update_label(self) -> str:
        if self._update_info:
            return f"新版 {self._update_info['latest']} あり"
        return f"アップデート確認 (v{__version__})"

    def _providers_submenu(self) -> Menu:
        def make_toggle(key: str):
            def toggle(_icon=None, _item=None):
                self.config.enabled[key] = not self.config.enabled.get(key, True)
                self.config.save()
                self._on_refresh()

            return toggle

        return Menu(
            *[
                MenuItem(
                    PROVIDER_NAMES[key],
                    make_toggle(key),
                    checked=lambda item, k=key: self.config.enabled.get(k, True),
                )
                for key in PROVIDER_KEYS
            ]
        )

    def _interval_submenu(self) -> Menu:
        def make_set(secs: int):
            def setter(_icon=None, _item=None):
                self.config.interval = secs
                self.config.save()
                self._wake.set()

            return setter

        return Menu(
            *[
                MenuItem(
                    label,
                    make_set(secs),
                    checked=lambda item, s=secs: self.config.interval == s,
                    radio=True,
                )
                for secs, label in INTERVAL_PRESETS
            ]
        )

    # ---- メニュー/クリックのコールバック（pystray スレッド → キュー整流） ----
    def _menu_toggle_panel(self, _icon=None, _item=None) -> None:
        self.ui_q.put(("toggle",))

    def _menu_check_update(self, _icon=None, _item=None) -> None:
        if self._update_info:
            webbrowser.open(self._update_info["url"])
        else:
            threading.Thread(target=self._check_update, args=(True,), daemon=True).start()

    def _check_update(self, open_if_found: bool = False) -> None:
        info = updater.check()
        if info:
            self._update_info = info
            self.icon.menu = self._build_menu()  # メニュー文言を更新
            if open_if_found:
                webbrowser.open(info["url"])

    def _menu_quit(self, _icon=None, _item=None) -> None:
        self.ui_q.put(("quit",))

    def _on_refresh(self) -> None:
        threading.Thread(target=self.refresh, daemon=True).start()

    # ---- Tk メインスレッド側のポンプ ----
    def _pump(self) -> None:
        try:
            while True:
                cmd = self.ui_q.get_nowait()
                self._handle_ui(cmd)
        except queue.Empty:
            pass
        if not self._stop.is_set():
            self.root.after(120, self._pump)

    def _handle_ui(self, cmd) -> None:
        name = cmd[0]
        with self.lock:
            results = list(self.results)
        if name == "toggle":
            self.panel.toggle(results, self.stats, on_refresh=self._on_refresh)
        elif name == "data":
            if self.panel.is_visible():
                self.panel.show(results, self.stats, on_refresh=self._on_refresh, steal_focus=False)
        elif name == "quit":
            self._stop.set()
            self._wake.set()
            try:
                self.icon.stop()
            except Exception:
                pass
            self.root.destroy()

    # ---- ポーリングループ（daemon スレッド） ----
    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.refresh()
            except Exception as e:
                # 想定外の例外でポーリングが恒久停止しないよう必ず継続する
                print(f"refresh エラー: {e}")
            self._wake.wait(self.config.interval)
            self._wake.clear()

    def run(self) -> None:
        self.icon.run_detached()  # 別スレッドでトレイ常駐、ブロックしない
        threading.Thread(target=self._poll_loop, daemon=True).start()
        threading.Thread(target=self._check_update, daemon=True).start()  # 起動時に静かに確認
        self.root.after(120, self._pump)
        self.root.mainloop()


if __name__ == "__main__":
    if acquire_single_instance():
        CodexBarApp().run()
    else:
        print("CodexBar は既に起動しています。")
