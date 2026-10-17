"""Create public, obviously fictional demonstration material."""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from id_watermark.core import create_watermarked, save_export
from id_watermark.visible import VisibleConfig, find_font

DEMO_PASSWORD = "DEMO-only-not-for-private-use"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--font", default="")
    args = p.parse_args()
    target = Path("examples")
    target.mkdir(exist_ok=True)
    font = find_font(args.font)
    image = Image.new("RGB", (1600, 1000), "#ede8df")
    d = ImageDraw.Draw(image)
    d.rounded_rectangle((22, 22, 1578, 978), radius=35, outline="#b4ada3", width=3)
    for y in range(80, 940, 18):
        d.line((50, y, 1550, y + 38), fill="#d5d0c7", width=1)
    large = ImageFont.truetype(font, 54)
    normal = ImageFont.truetype(font, 36)
    small = ImageFont.truetype(font, 24)
    d.text((75, 65), "离线水印功能演示 · 虚构材料", font=large, fill="#364952")
    d.rounded_rectangle((1050, 210, 1490, 770), radius=20, fill="#b7c4cb")
    d.ellipse((1190, 280, 1350, 440), fill="#eef0ef")
    d.rounded_rectangle((1130, 465, 1410, 705), radius=65, fill="#eef0ef")
    for y, text in [
        (240, "姓名：演示样例"),
        (350, "用途：办理供热入户手续"),
        (460, "日期：2026年10月"),
        (570, "所有信息均为虚构"),
        (680, "不包含真实身份证信息"),
    ]:
        d.text((90, y), text, font=normal, fill="#4c5357")
    d.text((90, 865), "DEMO ONLY / 仅用于软件测试，非证件", font=small, fill="#727b7c")
    image.save(target / "sample_document.png")
    cfg = VisibleConfig(font_path=font, font_size=40, gap_x=110, gap_y=100, opacity=0.27)
    out, receipt = create_watermarked(
        image, cfg, password=DEMO_PASSWORD, recipient="公开演示，非真实外发"
    )
    receipt["visible"]["font_path"] = "(system CJK font used for public demo)"
    _, sidecar = save_export(out, receipt, target / "sample_marked.png", overwrite=True)
    sidecar.replace(target / "demo_receipt.json")
    print("Public demo generated; password:", DEMO_PASSWORD)


if __name__ == "__main__":
    main()
