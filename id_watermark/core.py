"""File handling, export verification and scan geometry; all operations local."""

import hashlib
import json
import os
import secrets
import tempfile
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from . import HIDDEN_TEXT, __version__
from .frequency import (
    PROFILES,
    WatermarkError,
    capacity,
    embed_bgr,
    extract_bgr,
    new_parameters,
)
from .visible import VisibleConfig, apply_visible

MAX_PIXELS = 20_000_000
SCHEMA = "local-id-watermark-receipt-v1"


def clean_rgb(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    if image.width * image.height > MAX_PIXELS:
        raise ValueError("图像超过 2000 万像素，请先缩小。")
    rgba = image.convert("RGBA")
    white = Image.new("RGBA", rgba.size, "white")
    white.alpha_composite(rgba)
    # A fresh pixel object strips EXIF, GPS, thumbnails, comments and ICC metadata.
    return Image.fromarray(np.asarray(white.convert("RGB")).copy())


def load_image(path: str | Path) -> Image.Image:
    try:
        with Image.open(path) as im:
            if im.width * im.height > MAX_PIXELS:
                raise ValueError("图像超过 2000 万像素，请先缩小。")
            im.load()
            return clean_rgb(im)
    except (SyntaxError, Image.DecompressionBombError) as exc:
        raise ValueError("图片格式或 EXIF 信息损坏，请先重新保存照片。") from exc


def to_bgr(image: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2BGR)


def from_bgr(bgr: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def create_watermarked(
    image: Image.Image,
    visible: VisibleConfig | None = None,
    hidden: bool = True,
    hidden_text: str = HIDDEN_TEXT,
    password: str = "",
    profile: str = "strong",
    recipient: str = "",
    visible_trace: bool = False,
) -> tuple[Image.Image, dict]:
    if visible is None and not hidden:
        raise ValueError("请至少启用一种水印。")
    if len(recipient) > 200:
        raise ValueError("接收方备注请限制在 200 字以内。")
    if visible_trace and visible is None:
        raise ValueError("显示副本编号需要同时启用可见水印。")
    params, packet = new_parameters(password, hidden_text, profile) if hidden else (None, None)
    trace_id = params["trace_id"] if params else secrets.token_hex(8)
    if visible_trace:
        visible = replace(visible, text=f"{visible.text}\n副本编号：{trace_id}")
    image = clean_rgb(image)
    base = apply_visible(image, visible) if visible else image
    receipt = {
        "schema": SCHEMA,
        "app_version": __version__,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "image_size": list(base.size),
        "recipient_note": recipient,
        "trace_id": trace_id,
        "visible": asdict(visible) if visible else None,
        "frequency": None,
    }
    if hidden:
        marked = embed_bgr(to_bgr(base), password, params, packet)
        # Do not export a blind watermark that cannot survive its own PNG encoding.
        checked = extract_bgr(marked, password, params)
        if checked["text"] != hidden_text:
            raise WatermarkError("导出前提取校验未通过，请更换原图或频域强度。")
        params["repeat_count"] = capacity(base.size) // params["packet_bits"]
        receipt["frequency"] = params
        receipt["self_check"] = {"passed": True, "corrected_bytes": checked["corrected_bytes"]}
        result = from_bgr(marked)
    else:
        result = base
    return result, receipt


def save_export(
    image: Image.Image,
    receipt: dict,
    output: str | Path,
    source: str | Path | None = None,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    output = Path(output).expanduser().resolve()
    if output.suffix.lower() != ".png":
        raise ValueError("导出请使用 PNG，以免 JPEG 再压缩破坏频域水印。")
    if source and Path(source).expanduser().resolve() == output:
        raise ValueError("不能覆盖原始照片，请另存为新文件。")
    receipt_path = Path(str(output) + ".receipt.json")
    if not overwrite and (output.exists() or receipt_path.exists()):
        raise FileExistsError("输出文件或凭据已存在，请另选文件名。")
    output.parent.mkdir(parents=True, exist_ok=True)
    staged = []
    try:
        for _ in range(2):
            fd, path = tempfile.mkstemp(prefix=".idwm-", dir=output.parent)
            os.close(fd)
            staged.append(Path(path))
        # Fresh RGB image deliberately carries no original metadata.
        clean = Image.fromarray(np.asarray(image.convert("RGB")).copy())
        clean.save(staged[0], format="PNG", dpi=(300, 300))
        receipt = dict(receipt)
        receipt["output_sha256"] = hashlib.sha256(staged[0].read_bytes()).hexdigest()
        staged[1].write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(staged[0], output)
        os.replace(staged[1], receipt_path)
    finally:
        for path in staged:
            path.unlink(missing_ok=True)
    return output, receipt_path


def load_receipt(path: str | Path) -> dict:
    path = Path(path)
    if path.stat().st_size > 64_000:
        raise ValueError("提取凭据过大或格式不正确。")
    try:
        r = json.loads(path.read_text(encoding="utf-8"))
        if r["schema"] != SCHEMA:
            raise ValueError("不支持的提取凭据版本。")
        size = r["image_size"]
        if (
            not isinstance(size, list)
            or len(size) != 2
            or any(type(x) is not int or not 16 <= x <= 12000 for x in size)
            or size[0] * size[1] > MAX_PIXELS
        ):
            raise ValueError("凭据中的图像尺寸无效。")
        f = r["frequency"]
        if f is None:
            raise ValueError("这份副本只加了可见水印，没有频域水印。")
        if (
            f["algorithm"] != "luma-dwt-dct-svd-v1"
            or f["parity_bytes"] != 48
            or f["profile"] not in PROFILES
            or (f["d1"], f["d2"]) != PROFILES[f["profile"]]
        ):
            raise ValueError("凭据中的频域算法或强度无效。")
        if (
            type(f["packet_bits"]) is not int
            or not 632 <= f["packet_bits"] <= 15000
            or f["packet_bits"] % 8
            or f["packet_bits"] >= capacity(tuple(size))
        ):
            raise ValueError("凭据中的水印长度无效。")
        if len(bytes.fromhex(f["salt"])) != 16 or len(bytes.fromhex(f["trace_id"])) != 8:
            raise ValueError("凭据中的盐值或副本编号无效。")
        return r
    except (KeyError, TypeError, json.JSONDecodeError, AttributeError) as exc:
        raise ValueError("提取凭据损坏或格式不正确。") from exc


def rectify_scan(image: Image.Image, size: tuple[int, int], corners=None) -> Image.Image:
    """Corners describe the entire exported image: TL, TR, BR, BL, in pixels.

    They are NOT the card corners unless the card fills the complete export.
    Without corners, caller asserts that image contains only the full export.
    """
    if corners is None:
        return image.resize(size, Image.Resampling.LANCZOS) if image.size != size else image.copy()
    pts = np.asarray(corners, dtype=np.float32)
    if pts.shape != (4, 2) or not np.isfinite(pts).all():
        raise ValueError("请按左上、右上、右下、左下顺序指定四个角点。")
    if (
        np.any(pts < 0)
        or np.any(pts[:, 0] > image.width - 1)
        or np.any(pts[:, 1] > image.height - 1)
    ):
        raise ValueError("角点必须位于图片内。")
    if not cv2.isContourConvex(pts) or cv2.contourArea(pts) < 100:
        raise ValueError("四个角点需构成不交叉的完整四边形。")
    w, h = size
    dst = np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]])
    transform = cv2.getPerspectiveTransform(pts, dst)
    bgr = cv2.warpPerspective(
        to_bgr(image), transform, size, flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )
    return from_bgr(bgr)


def extract_watermark(image: Image.Image, receipt: dict, password: str, corners=None) -> dict:
    if not receipt.get("frequency"):
        raise ValueError("此凭据没有频域水印信息。")
    aligned = rectify_scan(clean_rgb(image), tuple(receipt["image_size"]), corners)
    result = extract_bgr(to_bgr(aligned), password, receipt["frequency"])
    result["recipient_note_from_receipt"] = receipt.get("recipient_note", "")
    result["notice"] = "完整性校验通过；这是副本标记，不是不可伪造的身份或法律证明。"
    return result
