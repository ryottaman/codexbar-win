"""クリックで開くポップアップパネル（Tkinter）。

本家 CodexBar の macOS ポップオーバーを模したタブ UI。
- 概要タブ: 全媒体の主要メーター + 推定コスト/トークン合計
- 媒体タブ: 詳細メーター + 枯渇予測 + クレジット消費額、Claude は日次トークンの棒グラフ

スレッド注意: このモジュールの操作はすべて Tk メインスレッド上でのみ呼ぶこと。
"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont

import history
import usage_stats

BG = "#fafafa"
FG = "#1c1c1e"
SUB = "#8a8a8e"
SEP = "#ececec"
TRACK = "#e6e6e6"
BORDER = "#d0d0d0"
ACCENT = "#3a7afe"
BAR_BLUE = "#5b9bd5"

FONT_FAMILY = "Yu Gothic UI"
WIDTH = 344


def color_for(pct: float) -> str:
    if pct >= 90:
        return "#e84142"
    if pct >= 70:
        return "#f5a623"
    return "#2ecc71"


def _round_bar(canvas, x1, y1, x2, y2, color):
    r = (y2 - y1) / 2
    if x2 - x1 < 2 * r:
        x2 = x1 + 2 * r
    canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=color, outline=color)
    canvas.create_oval(x1, y1, x1 + 2 * r, y2, fill=color, outline=color)
    canvas.create_oval(x2 - 2 * r, y1, x2, y2, fill=color, outline=color)


class Panel:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.win: tk.Toplevel | None = None
        self.results = []
        self.stats = None
        self.on_refresh = None
        self.active_tab = "概要"
        self.content: tk.Frame | None = None
        self.fx_rate: float | None = None  # USD/JPY。None なら USD 表示

        self.f_title = tkfont.Font(family=FONT_FAMILY, size=11, weight="bold")
        self.f_provider = tkfont.Font(family=FONT_FAMILY, size=12, weight="bold")
        self.f_tab = tkfont.Font(family=FONT_FAMILY, size=9)
        self.f_tab_on = tkfont.Font(family=FONT_FAMILY, size=9, weight="bold")
        self.f_label = tkfont.Font(family=FONT_FAMILY, size=9)
        self.f_pct = tkfont.Font(family=FONT_FAMILY, size=10, weight="bold")
        self.f_sub = tkfont.Font(family=FONT_FAMILY, size=8)
        self.f_big = tkfont.Font(family=FONT_FAMILY, size=15, weight="bold")

    def _cost(self, usd: float) -> str:
        """コストを円建てで整形（レート未取得時は USD）。"""
        if self.fx_rate:
            return f"¥{usd * self.fx_rate:,.0f}"
        return f"${usd:,.2f}"

    # ---- 表示制御 ----
    def is_visible(self) -> bool:
        return bool(self.win and self.win.winfo_exists() and self.win.winfo_viewable())

    def toggle(self, results, stats=None, on_refresh=None, fx_rate=None):
        if self.is_visible():
            self.hide()
        else:
            self.show(results, stats, on_refresh, fx_rate=fx_rate)

    def hide(self):
        if self.win and self.win.winfo_exists():
            self.win.withdraw()

    def show(self, results, stats=None, on_refresh=None, steal_focus=True, fx_rate=None):
        self.results = results
        self.stats = stats
        self.on_refresh = on_refresh
        self.fx_rate = fx_rate
        # タブの有効性チェック（無効になった媒体を選んでいたら概要へ）
        valid = ["概要"] + [r.provider for r in results]
        if self.active_tab not in valid:
            self.active_tab = "概要"

        if self.win and self.win.winfo_exists():
            self.win.destroy()
        w = tk.Toplevel(self.root)
        self.win = w
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=BORDER)

        outer = tk.Frame(w, bg=BG)
        outer.pack(padx=1, pady=1, fill="both", expand=True)
        self._build(outer)

        w.update_idletasks()
        self._position(w)
        w.deiconify()
        if steal_focus:
            # データ更新による再描画ではフォーカスを奪わない
            w.focus_force()
        w.bind("<Escape>", lambda e: self.hide())
        w.bind("<FocusOut>", self._on_focus_out)

    def _on_focus_out(self, _e):
        try:
            focused = self.win.focus_get() if self.win else None
        except KeyError:
            # 他アプリのウィジェットにフォーカスが移ると Tk が KeyError を出すことがある
            focused = None
        if self.win and focused is None:
            self.hide()

    def _position(self, w):
        w.update_idletasks()
        ww, wh = w.winfo_width(), w.winfo_height()
        sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
        w.geometry(f"+{max(0, sw - ww - 16)}+{max(0, sh - wh - 56)}")

    # ---- 骨組み ----
    def _build(self, parent):
        # ヘッダー
        head = tk.Frame(parent, bg=BG)
        head.pack(fill="x", padx=14, pady=(12, 6))
        tk.Label(head, text="CodexBar", bg=BG, fg=FG, font=self.f_title).pack(side="left")

        close = tk.Label(head, text="✕", bg=BG, fg=SUB, font=self.f_label, cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: self.hide())
        refresh = tk.Label(head, text="⟳", bg=BG, fg=ACCENT, font=self.f_provider, cursor="hand2")
        refresh.pack(side="right", padx=(0, 10))
        refresh.bind("<Button-1>", lambda e: self.on_refresh() if self.on_refresh else None)

        # タブバー
        tabs = tk.Frame(parent, bg=BG)
        tabs.pack(fill="x", padx=10)
        names = ["概要"] + [r.provider for r in self.results]
        for name in names:
            on = name == self.active_tab
            lbl = tk.Label(
                tabs,
                text=name,
                bg=BG,
                fg=(ACCENT if on else SUB),
                font=(self.f_tab_on if on else self.f_tab),
                cursor="hand2",
                padx=8,
                pady=4,
            )
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda e, n=name: self._select(n))
        tk.Frame(parent, bg=SEP, height=1).pack(fill="x", pady=(2, 0))

        # コンテンツ
        self.content = tk.Frame(parent, bg=BG, width=WIDTH)
        self.content.pack(fill="both", expand=True)
        self._render()

    def _select(self, name):
        self.active_tab = name
        # コンテンツだけ差し替え（タブの見た目も更新するため全体再描画）
        for child in self.win.winfo_children():
            child.destroy()
        outer = tk.Frame(self.win, bg=BG)
        outer.pack(padx=1, pady=1, fill="both", expand=True)
        self._build(outer)
        self.win.update_idletasks()
        self._position(self.win)

    def _render(self):
        if self.active_tab == "概要":
            self._tab_overview(self.content)
        else:
            r = next((x for x in self.results if x.provider == self.active_tab), None)
            if r:
                self._tab_provider(self.content, r)

    # ---- 概要タブ ----
    def _tab_overview(self, parent):
        # 推定コスト/トークン
        if self.stats is not None:
            box = tk.Frame(parent, bg=BG)
            box.pack(fill="x", padx=14, pady=(10, 4))
            left = tk.Frame(box, bg=BG)
            left.pack(side="left")
            tk.Label(left, text="今日の推定コスト", bg=BG, fg=SUB, font=self.f_sub).pack(anchor="w")
            tk.Label(left, text=self._cost(self.stats.today_cost), bg=BG, fg=FG, font=self.f_big).pack(anchor="w")
            if self.fx_rate:
                tk.Label(left, text=f"${self.stats.today_cost:,.2f}", bg=BG, fg=SUB, font=self.f_sub).pack(anchor="w")
            right = tk.Frame(box, bg=BG)
            right.pack(side="right")
            tk.Label(right, text="過去30日", bg=BG, fg=SUB, font=self.f_sub).pack(anchor="e")
            tk.Label(right, text=self._cost(self.stats.total_cost), bg=BG, fg=FG, font=self.f_big).pack(anchor="e")
            if self.fx_rate:
                tk.Label(right, text=f"${self.stats.total_cost:,.0f}", bg=BG, fg=SUB, font=self.f_sub).pack(anchor="e")
            tk.Label(
                parent,
                text=f"30日トークン {usage_stats.fmt_tokens(self.stats.total_tokens)}（Claude Code ログから推定）",
                bg=BG, fg=SUB, font=self.f_sub,
            ).pack(anchor="w", padx=14)
        else:
            tk.Label(parent, text="コスト集計中…", bg=BG, fg=SUB, font=self.f_sub).pack(anchor="w", padx=14, pady=8)

        tk.Frame(parent, bg=SEP, height=1).pack(fill="x", padx=14, pady=(8, 0))

        # 各媒体の主要メーター
        for r in self.results:
            row = tk.Frame(parent, bg=BG)
            row.pack(fill="x", padx=14, pady=(8, 0))
            tk.Label(row, text=r.provider, bg=BG, fg=FG, font=self.f_label, width=8, anchor="w").pack(side="left")
            if r.ok and r.meters:
                worst = max(r.meters, key=lambda m: m.used_percent)
                pct = worst.used_percent
                tk.Label(row, text=f"{int(round(pct))}%", bg=BG, fg=color_for(pct), font=self.f_pct, width=5).pack(side="right")
                c = tk.Canvas(row, width=180, height=7, bg=BG, highlightthickness=0)
                c.pack(side="right", padx=(0, 6))
                _round_bar(c, 0, 0, 180, 7, TRACK)
                if pct > 0:
                    _round_bar(c, 0, 0, max(7, 180 * pct / 100), 7, color_for(pct))
            else:
                msg = "取得済" if r.ok else (r.error or "—")
                tk.Label(row, text=msg, bg=BG, fg=SUB, font=self.f_sub).pack(side="right")
        tk.Frame(parent, bg=BG, height=10).pack()

    # ---- 媒体タブ ----
    def _tab_provider(self, parent, r):
        top = tk.Frame(parent, bg=BG)
        top.pack(fill="x", padx=14, pady=(10, 2))
        tk.Label(top, text=r.provider, bg=BG, fg=FG, font=self.f_provider).pack(side="left")
        plan = r.extra.get("plan_type") if r.ok else None
        sub = r.extra.get("subscription")
        if plan or sub:
            tk.Label(top, text=str(plan or sub), bg=BG, fg=SUB, font=self.f_sub).pack(side="right")

        if not r.ok:
            tk.Label(parent, text=r.error or "取得失敗", bg=BG, fg=SUB, font=self.f_label).pack(anchor="w", padx=14, pady=(6, 12))
            return

        for m in r.meters:
            self._meter(parent, r.provider, m)

        for note in r.notes:
            tk.Label(parent, text=note, bg=BG, fg=SUB, font=self.f_sub).pack(anchor="w", padx=14, pady=(6, 0))

        # クレジット消費額（Claude spend）。公式値は USD 建てなので USD を主表示。
        spend = r.extra.get("spend")
        if spend and spend.get("limit"):
            tk.Frame(parent, bg=SEP, height=1).pack(fill="x", padx=14, pady=(10, 6))
            row = tk.Frame(parent, bg=BG)
            row.pack(fill="x", padx=14)
            tk.Label(row, text="クレジット消費", bg=BG, fg=SUB, font=self.f_sub).pack(side="left")
            tk.Label(
                row,
                text=f"${spend['used']:.2f} / ${spend['limit']:.2f}",
                bg=BG, fg=FG, font=self.f_label,
            ).pack(side="right")
            if self.fx_rate:
                tk.Label(
                    parent,
                    text=f"≈ ¥{spend['used'] * self.fx_rate:,.0f} / ¥{spend['limit'] * self.fx_rate:,.0f}",
                    bg=BG, fg=SUB, font=self.f_sub,
                ).pack(anchor="e", padx=14)

        # Claude タブは日次トークンの棒グラフ + コスト
        if r.provider == "Claude" and self.stats is not None:
            tk.Frame(parent, bg=SEP, height=1).pack(fill="x", padx=14, pady=(10, 6))
            info = tk.Frame(parent, bg=BG)
            info.pack(fill="x", padx=14)
            tk.Label(info, text="今日", bg=BG, fg=SUB, font=self.f_sub).pack(side="left")
            tk.Label(
                info,
                text=f"{usage_stats.fmt_tokens(self.stats.today_tokens)} / {self._cost(self.stats.today_cost)} 推定",
                bg=BG, fg=FG, font=self.f_label,
            ).pack(side="right")
            self._chart(parent, self.stats.daily_series(14))
            tk.Label(
                parent,
                text="※コストは公開価格からの概算です",
                bg=BG, fg=SUB, font=self.f_sub,
            ).pack(anchor="w", padx=14, pady=(4, 0))

        tk.Frame(parent, bg=BG, height=10).pack()

    def _meter(self, parent, provider, m):
        pct = max(0.0, min(100.0, m.used_percent))
        mf = tk.Frame(parent, bg=BG)
        mf.pack(fill="x", padx=14, pady=(8, 0))

        line1 = tk.Frame(mf, bg=BG)
        line1.pack(fill="x")
        tk.Label(line1, text=m.label, bg=BG, fg=FG, font=self.f_label).pack(side="left")
        reset = m.reset_in_text()
        if reset:
            tk.Label(line1, text=f"{reset}でリセット", bg=BG, fg=SUB, font=self.f_sub).pack(side="right")

        line2 = tk.Frame(mf, bg=BG)
        line2.pack(fill="x", pady=(3, 0))
        tk.Label(line2, text=f"{int(round(pct))}%", bg=BG, fg=color_for(pct), font=self.f_pct, width=5).pack(side="right")
        c = tk.Canvas(line2, width=250, height=8, bg=BG, highlightthickness=0)
        c.pack(side="left", fill="x", expand=True)
        _round_bar(c, 0, 0, 250, 8, TRACK)
        if pct > 0:
            _round_bar(c, 0, 0, max(8, 250 * pct / 100), 8, color_for(pct))

        # 枯渇予測
        eta = history.eta_text(provider, m.label, pct)
        if eta:
            tk.Label(mf, text=eta, bg=BG, fg=color_for(pct), font=self.f_sub).pack(anchor="w", pady=(2, 0))

    def _chart(self, parent, series):
        # series: [(date, tokens, cost), ...] 古い順
        H = 64
        W = WIDTH - 28
        c = tk.Canvas(parent, width=W, height=H + 14, bg=BG, highlightthickness=0)
        c.pack(padx=14, pady=(6, 0))
        if not series:
            return
        mx = max((t for _, t, _ in series), default=0) or 1
        n = len(series)
        gap = 3
        bw = (W - gap * (n - 1)) / n
        for i, (d, tok, cost) in enumerate(series):
            x1 = i * (bw + gap)
            x2 = x1 + bw
            bh = (tok / mx) * H
            y2 = H
            y1 = H - bh
            col = BAR_BLUE if tok > 0 else TRACK
            c.create_rectangle(x1, y1, x2, y2, fill=col, outline=col)
        # 両端の日付
        c.create_text(0, H + 7, text=series[0][0][5:], anchor="w", fill=SUB, font=self.f_sub)
        c.create_text(W, H + 7, text=series[-1][0][5:], anchor="e", fill=SUB, font=self.f_sub)
