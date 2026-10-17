"""Behavior tests use only synthetic documents, never personal ID data."""

import json
import os
from dataclasses import replace

import numpy as np
import pytest
from PIL import Image, ImageDraw

from id_watermark import HIDDEN_TEXT
from id_watermark.core import (
    create_watermarked,
    extract_watermark,
    load_image,
    load_receipt,
    rectify_scan,
    save_export,
)
from id_watermark.frequency import WatermarkError, pack_message, unpack_message
from id_watermark.visible import VisibleConfig, apply_visible

PASSWORD = "demo-only-password-123"
FONT = os.environ.get("IDWM_TEST_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


@pytest.fixture(scope="module")
def synthetic():
    im = Image.new("RGB", (1200, 760), "#e8dfd1")
    d = ImageDraw.Draw(im)
    for y in range(0, 760, 20):
        d.line((0, y, 1200, y + 60), fill="#c1c1ba", width=1)
    d.rounded_rectangle((55, 120, 355, 640), radius=25, fill="#8caabc")
    for y in range(160, 650, 75):
        d.rectangle((430, y, 1050, y + 12), fill="#4a4947")
    return im


@pytest.fixture(scope="module")
def marked(synthetic):
    cfg = VisibleConfig(text="DEMO / SAMPLE ONLY", font_path=FONT, font_size=30)
    image, receipt = create_watermarked(synthetic, cfg, password=PASSWORD, recipient="TEST ONLY")
    return image, receipt


def test_unicode_packet_corrects_24_damaged_bytes():
    key = b"test-key" * 4
    data = bytearray(pack_message(HIDDEN_TEXT, "0123456789abcdef", key))
    for i in range(24):
        data[i * 3] ^= 0x6B
    result = unpack_message(bytes(data), key)
    assert result["text"] == HIDDEN_TEXT
    assert result["trace_id"] == "0123456789abcdef"
    assert result["corrected_bytes"] == 24
    with pytest.raises(WatermarkError):
        unpack_message(bytes(data), b"wrong-key")


def test_png_export_extract_and_strip_private_metadata(marked, tmp_path):
    image, receipt = marked
    image = image.copy()
    private_exif = Image.Exif()
    private_exif[315] = "PRIVATE USER"
    image.info["exif"] = private_exif.tobytes()
    out, sidecar = save_export(image, receipt, tmp_path / "中文副本.png")
    reread = load_receipt(sidecar)
    result = extract_watermark(load_image(out), reread, PASSWORD)
    assert result["text"] == HIDDEN_TEXT
    assert result["integrity_verified"] is True
    assert result["recipient_note_from_receipt"] == "TEST ONLY"
    with Image.open(out) as im:
        assert not im.getexif()
        assert "exif" not in im.info
    assert "password" not in json.dumps(reread)
    assert len(reread["output_sha256"]) == 64
    with pytest.raises(FileExistsError):
        save_export(image, receipt, out)
    with pytest.raises(ValueError, match="覆盖原始"):
        save_export(image, receipt, out, source=out, overwrite=True)


def test_grayscale_retains_luminance_mark(marked):
    image, receipt = marked
    result = extract_watermark(image.convert("L").convert("RGB"), receipt, PASSWORD)
    assert result["text"] == HIDDEN_TEXT


def test_wrong_password_and_unmarked_image_never_report_success(marked, synthetic):
    image, receipt = marked
    with pytest.raises(WatermarkError):
        extract_watermark(image, receipt, "wrong-password-123")
    with pytest.raises(WatermarkError):
        extract_watermark(synthetic, receipt, PASSWORD)


def test_unique_trace_ids(synthetic):
    _, r1 = create_watermarked(synthetic, password=PASSWORD)
    _, r2 = create_watermarked(synthetic, password=PASSWORD)
    assert r1["frequency"]["trace_id"] != r2["frequency"]["trace_id"]
    assert r1["frequency"]["salt"] != r2["frequency"]["salt"]


def test_visible_only_hidden_only_and_no_mode(synthetic):
    cfg = VisibleConfig(text="SAMPLE", layout="single", font_path=FONT)
    image, receipt = create_watermarked(synthetic, cfg, hidden=False)
    assert receipt["frequency"] is None
    assert not np.array_equal(np.array(image), np.array(synthetic))
    with pytest.raises(ValueError):
        create_watermarked(synthetic, hidden=False)


def test_optional_visible_trace_matches_embedded_id(synthetic):
    cfg = VisibleConfig(text="SAMPLE", font_path=FONT)
    image, receipt = create_watermarked(synthetic, cfg, password=PASSWORD, visible_trace=True)
    result = extract_watermark(image, receipt, PASSWORD)
    assert result["trace_id"] == receipt["trace_id"]
    assert receipt["trace_id"] in receipt["visible"]["text"]


def test_visible_position_and_density(synthetic):
    cfg = VisibleConfig(text="SAMPLE", layout="single", angle=0, font_path=FONT)
    left = np.any(
        np.array(apply_visible(synthetic, replace(cfg, x=0))) != np.array(synthetic), axis=2
    )
    right = np.any(
        np.array(apply_visible(synthetic, replace(cfg, x=1))) != np.array(synthetic), axis=2
    )
    assert np.nonzero(left)[1].mean() < 200
    assert np.nonzero(right)[1].mean() > 1000
    dense = apply_visible(synthetic, replace(cfg, layout="tile", gap_x=10, gap_y=10))
    sparse = apply_visible(synthetic, replace(cfg, layout="tile", gap_x=300, gap_y=150))
    assert np.count_nonzero(np.array(dense) != np.array(synthetic)) > np.count_nonzero(
        np.array(sparse) != np.array(synthetic)
    )


def test_scan_frame_recovers_translation_after_four_corners(marked):
    image, receipt = marked
    scan = Image.new("RGB", (1340, 900), "white")
    scan.paste(image, (60, 70))
    corners = [(60, 70), (1259, 70), (1259, 829), (60, 829)]
    result = extract_watermark(scan, receipt, PASSWORD, corners)
    assert result["text"] == HIDDEN_TEXT
    with pytest.raises(WatermarkError):
        extract_watermark(scan, receipt, PASSWORD)


def test_bad_geometry_small_image_and_credentials(marked, tmp_path):
    image, receipt = marked
    with pytest.raises(ValueError):
        rectify_scan(image, image.size, [(0, 0)] * 4)
    with pytest.raises(ValueError):
        create_watermarked(Image.new("RGB", (120, 80)), password=PASSWORD)
    receipt["frequency"]["packet_bits"] += 1
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(receipt))
    try:
        with pytest.raises(ValueError):
            load_receipt(path)
    finally:
        receipt["frequency"]["packet_bits"] -= 1


def test_exif_orientation_is_applied_and_removed(tmp_path):
    image = Image.new("RGB", (40, 20), "white")
    exif = Image.Exif()
    exif[274] = 6
    exif[315] = "PRIVATE USER"
    path = tmp_path / "rotated.jpg"
    image.save(path, exif=exif)
    loaded = load_image(path)
    assert loaded.size == (20, 40)
    assert len(loaded.getexif()) == 0
