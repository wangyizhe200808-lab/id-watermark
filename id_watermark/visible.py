"""Visible marks are rasterized directly into a new RGB image."""

import os
from dataclasses import dataclass
from math import ceil, hypot
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont

from . import VISIBLE_TEXT


@dataclass(frozen=True)
class VisibleConfig:
    text: str = VISIBLE_TEXT
    layout: str = "tile"
    font_size: int = 32
    opacity: float = 0.24
    angle: float = -25
    gap_x: int = 100
    gap_y: int = 70
    x: float = 0.5
    y: float = 0.5
    color: str = "#b02232"
    font_path: str = ""


def find_font(explicit: str = "") -> str:
    """Prefer an installed CJK font; never silently replace Chinese with boxes."""
    if explicit:
        if not Path(explicit).is_file():
            raise ValueError("字体文件不存在，请选择 TTF / TTC / OTF 字体。")
        return explicit
    roots = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/simhei.ttf",
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    ]
    for p in roots:
        if p.is_file():
            return str(p)
    raise ValueError("未找到中文字体。请在界面选择微软雅黑、思源黑体等中文字体文件。")


def apply_visible(image: Image.Image, cfg: VisibleConfig) -> Image.Image:
    if not cfg.text.strip():
        raise ValueError("可见水印文字不能为空。")
    if cfg.layout not in {"tile", "single"}:
        raise ValueError("排布只能为 tile 或 single。")
    if not (8 <= cfg.font_size <= 400 and 0 <= cfg.opacity <= 1):
        raise ValueError("字号范围为 8–400，透明度范围为 0–1。")
    if not (0 <= cfg.x <= 1 and 0 <= cfg.y <= 1 and -180 <= cfg.angle <= 180):
        raise ValueError("位置比例需在 0–1 之间，角度需在 -180–180 之间。")
    if not (0 <= cfg.gap_x <= 2000 and 0 <= cfg.gap_y <= 2000):
        raise ValueError("水印间距需在 0–2000 像素之间。")
    if len(cfg.text) > 200:
        raise ValueError("可见水印请限制在 200 字以内，可使用换行。")
    base = image.convert("RGBA")
    font = ImageFont.truetype(find_font(cfg.font_path), cfg.font_size)
    rgba = (*ImageColor.getrgb(cfg.color), round(cfg.opacity * 255))
    box = ImageDraw.Draw(base).multiline_textbbox((0, 0), cfg.text, font=font, spacing=4)
    tw, th = box[2] - box[0], box[3] - box[1]
    stamp = Image.new("RGBA", (tw + 8, th + 8))
    ImageDraw.Draw(stamp).multiline_text(
        (4 - box[0], 4 - box[1]), cfg.text, font=font, fill=rgba, spacing=4
    )
    w, h = base.size
    if cfg.layout == "single":
        overlay = Image.new("RGBA", base.size)
        stamp = stamp.rotate(cfg.angle, resample=Image.Resampling.BICUBIC, expand=True)
        # Endpoints keep a fitting stamp fully inside the image.
        px = round((w - stamp.width) * cfg.x)
        py = round((h - stamp.height) * cfg.y)
        overlay.alpha_composite(stamp, (px, py))
    else:
        side = ceil(hypot(w, h)) + 4
        if side * side > 55_000_000:
            raise ValueError("平铺水印画布过大，请先将照片缩小至约 2000–4000 像素。")
        layer = Image.new("RGBA", (side, side))
        sx, sy = stamp.width + cfg.gap_x, stamp.height + cfg.gap_y
        # x/y shift the complete pattern by one tile period.
        ox = round(cfg.x * sx) % sx
        oy = round(cfg.y * sy) % sy
        for y in range(oy - sy, side, sy):
            for x in range(ox - sx, side, sx):
                layer.alpha_composite(stamp, (x, y))
        layer = layer.rotate(cfg.angle, resample=Image.Resampling.BICUBIC)
        left, top = (side - w) // 2, (side - h) // 2
        overlay = layer.crop((left, top, left + w, top + h))
    return Image.alpha_composite(base, overlay).convert("RGB")
