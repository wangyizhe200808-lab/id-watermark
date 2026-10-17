"""Reproducible DIGITAL experiments; NOT evidence of print/scan robustness."""

import json
import platform
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageFilter

from id_watermark.core import extract_watermark, load_image, load_receipt
from scripts.make_demo import DEMO_PASSWORD


def jpeg(im, quality):
    buf = BytesIO()
    im.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    with Image.open(buf) as reread:
        return reread.convert("RGB")


def main():
    image = load_image("examples/sample_marked.png")
    receipt = load_receipt("examples/demo_receipt.json")
    gray = image.convert("L").convert("RGB")
    rng = np.random.default_rng(20261017)
    mild = np.clip(
        np.asarray(gray.filter(ImageFilter.GaussianBlur(0.35))).astype(float)
        + rng.normal(0, 0.8, (image.height, image.width, 3)),
        0,
        255,
    ).astype("uint8")
    harsh = np.clip(
        np.asarray(gray.filter(ImageFilter.GaussianBlur(0.8))).astype(float) * 1.05
        + 6
        + rng.normal(0, 2.0, (image.height, image.width, 3)),
        0,
        255,
    ).astype("uint8")
    shifted = Image.new("RGB", (image.width + 180, image.height + 160), "white")
    shifted.paste(image, (80, 70))
    corners = [
        (80, 70),
        (80 + image.width - 1, 70),
        (80 + image.width - 1, 70 + image.height - 1),
        (80, 70 + image.height - 1),
    ]
    cases = [
        ("original_png", image, None),
        ("jpeg_quality_85", jpeg(image, 85), None),
        ("grayscale", gray, None),
        (
            "black_white_threshold_170",
            gray.point(lambda p: 255 if p > 170 else 0).convert("RGB"),
            None,
        ),
        (
            "rotation_1_degree_without_sync",
            image.rotate(1, resample=Image.Resampling.BICUBIC, fillcolor="white"),
            None,
        ),
        (
            "resize_75_percent_then_restore",
            image.resize((image.width * 3 // 4, image.height * 3 // 4), Image.Resampling.LANCZOS),
            None,
        ),
        ("mild_blur_and_noise_digital_only", Image.fromarray(mild), None),
        (
            "stronger_blur_brightness_noise_jpeg_digital_only",
            jpeg(Image.fromarray(harsh), 75),
            None,
        ),
        ("scan_border_without_alignment", shifted, None),
        ("scan_border_with_exact_four_corners", shifted, corners),
        ("unmarked_negative_control", load_image("examples/sample_document.png"), None),
    ]
    results = []
    expected = "仅限办理供热入户手续使用，2026年10月"
    for name, attacked, points in cases:
        try:
            result = extract_watermark(attacked, receipt, DEMO_PASSWORD, points)
            ok = result["text"] == expected
            item = {
                "case": name,
                "watermark_recovered": ok,
                "corrected_bytes": result["corrected_bytes"],
            }
        except ValueError as exc:
            item = {"case": name, "watermark_recovered": False, "error": str(exc)}
        results.append(item)
        print(name, item["watermark_recovered"])
    original = np.asarray(load_image("examples/sample_document.png"), dtype=float)
    marked = np.asarray(image, dtype=float)
    mse = float(np.mean((original - marked) ** 2))
    summary = {
        "python": platform.python_version(),
        "opencv": cv2.__version__,
        "image_size": list(image.size),
        "profile": receipt["frequency"]["profile"],
        "note": "单张虚构样图的数字实验；没有进行真实打印、扫描或复印验证。",
        "combined_visible_and_hidden_psnr_db": round(10 * np.log10(255**2 / mse), 2),
        "cases": results,
    }
    Path("docs").mkdir(exist_ok=True)
    Path("docs/robustness_results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
