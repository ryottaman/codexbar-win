"""トレイアイコン生成。

最も逼迫している利用率をリング状のメーターで描画し、
しきい値で色を変える（緑→黄→赤）。CodexBar のメニューバー表示の代替。

4 倍解像度で描画してから縮小することでアンチエイリアスを効かせ、
リングは丸端、中央に使用率の整数値を表示する。
"""
from __future__ import annotations

from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

OUT = 64  # 出力サイズ
SS = 4    # スーパーサンプリング倍率
SIZE = OUT * SS

TRACK = (100, 100, 100, 90)   # 背景リング
TEXT = (245, 245, 245, 255)   # 数字


def color_for(percent: float) -> tuple[int, int, int]:
    """使用率に応じた色を返す。"""
    if percent >= 90:
        return (232, 65, 66)    # 赤
    if percent >= 70:
        return (245, 166, 35)   # 黄
    return (46, 204, 113)       # 緑


@lru_cache(maxsize=4)
def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "seguisb.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _rounded_arc(d: ImageDraw.ImageDraw, box, start, end, fill, width):
    """丸端のアークを描く（線幅ぶんの円を両端に足す）。"""
    d.arc(box, start, end, fill=fill, width=width)


def make_icon(percent: float | None, error: bool = False) -> Image.Image:
    """使用率(0-100)を表すリングアイコンを生成する。"""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    margin = 8 * SS
    box = (margin, margin, SIZE - margin, SIZE - margin)
    width = 9 * SS

    if error or percent is None:
        d.arc(box, 0, 360, fill=(120, 120, 120, 110), width=width)
        # 赤い×
        cx = SIZE // 2
        r = 12 * SS
        lw = 6 * SS
        d.line((cx - r, cx - r, cx + r, cx + r), fill=(232, 65, 66, 255), width=lw)
        d.line((cx + r, cx - r, cx - r, cx + r), fill=(232, 65, 66, 255), width=lw)
        return img.resize((OUT, OUT), Image.LANCZOS)

    pct = max(0.0, min(100.0, percent))
    col = color_for(pct) + (255,)

    # 背景トラック（フルリング）
    d.arc(box, 0, 360, fill=TRACK, width=width)

    # 使用率アーク（12時起点・時計回り）
    start = -90
    end = start + 360 * pct / 100
    if end > start:
        d.arc(box, start, end, fill=col, width=width)
        # 両端を丸く（アークの端に小円を描く）
        import math

        cx = cy = SIZE / 2
        rad = (SIZE - 2 * margin) / 2
        for ang in (start, end):
            ax = cx + rad * math.cos(math.radians(ang))
            ay = cy + rad * math.sin(math.radians(ang))
            rr = width / 2
            d.ellipse((ax - rr, ay - rr, ax + rr, ay + rr), fill=col)

    # 中央に整数％（桁数でフォントサイズを調整し、濃い縁取りで明暗どちらの
    # タスクバーでも読めるようにする）
    text = str(int(round(pct)))
    font_px = (30 if len(text) <= 2 else 24) * SS
    font = _font(font_px)
    stroke = 3 * SS
    bbox = d.textbbox((0, 0), text, font=font, stroke_width=stroke)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(
        ((SIZE - tw) / 2 - bbox[0], (SIZE - th) / 2 - bbox[1]),
        text,
        fill=TEXT,
        font=font,
        stroke_width=stroke,
        stroke_fill=(20, 20, 20, 235),
    )

    return img.resize((OUT, OUT), Image.LANCZOS)
