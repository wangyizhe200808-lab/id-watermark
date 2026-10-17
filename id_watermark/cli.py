"""A CLI kept separate from Tk so it works on headless machines."""

import argparse
import getpass
import json
import os
import sys

from . import HIDDEN_TEXT, VISIBLE_TEXT
from .core import create_watermarked, extract_watermark, load_image, load_receipt, save_export
from .visible import VisibleConfig


def get_password(args):
    if args.password_env:
        value = os.environ.get(args.password_env, "")
        if not value:
            raise ValueError(f"环境变量 {args.password_env} 未设置。")
        return value
    return getpass.getpass("频域水印密码（至少 8 位）：")


def parser():
    p = argparse.ArgumentParser(description="本地证件水印：可见 + DWT-DCT-SVD 频域水印")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("gui", help="启动桌面界面")
    e = sub.add_parser("embed", help="生成水印 PNG 和本地提取凭据")
    e.add_argument("input")
    e.add_argument("output")
    e.add_argument("--mode", choices=["both", "visible", "hidden"], default="both")
    e.add_argument("--visible-text", default=VISIBLE_TEXT)
    e.add_argument("--hidden-text", default=HIDDEN_TEXT)
    e.add_argument("--layout", choices=["tile", "single"], default="tile")
    e.add_argument("--font", default="")
    e.add_argument("--font-size", type=int, default=32)
    e.add_argument("--opacity", type=float, default=0.24)
    e.add_argument("--angle", type=float, default=-25)
    e.add_argument("--gap-x", type=int, default=100)
    e.add_argument("--gap-y", type=int, default=70)
    e.add_argument("--x", type=float, default=0.5)
    e.add_argument("--y", type=float, default=0.5)
    e.add_argument("--color", default="#b02232")
    e.add_argument("--strength", choices=["balanced", "strong", "print"], default="strong")
    e.add_argument("--recipient", default="", help="接收方备注，仅存本地凭据")
    e.add_argument(
        "--visible-trace", action="store_true", help="在可见水印中附加副本编号，便于纸面核对"
    )
    e.add_argument("--password-env", help="从指定环境变量取密码；不设置则安全询问")
    e.add_argument("--overwrite", action="store_true")
    d = sub.add_parser("extract", help="提取并校验频域水印")
    d.add_argument("image")
    d.add_argument("receipt")
    d.add_argument("--password-env")
    d.add_argument(
        "--corners",
        type=float,
        nargs=8,
        metavar="XY",
        help="完整外发图像的四角：左上 右上 右下 左下，共 8 个像素坐标",
    )
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "gui":
            from .gui import main as gui_main

            gui_main()
            return 0
        if args.command == "embed":
            visible = None
            if args.mode != "hidden":
                visible = VisibleConfig(
                    text=args.visible_text,
                    layout=args.layout,
                    font_path=args.font,
                    font_size=args.font_size,
                    opacity=args.opacity,
                    angle=args.angle,
                    gap_x=args.gap_x,
                    gap_y=args.gap_y,
                    x=args.x,
                    y=args.y,
                    color=args.color,
                )
            password = get_password(args) if args.mode != "visible" else ""
            image, receipt = create_watermarked(
                load_image(args.input),
                visible=visible,
                hidden=args.mode != "visible",
                hidden_text=args.hidden_text,
                password=password,
                profile=args.strength,
                recipient=args.recipient,
                visible_trace=args.visible_trace,
            )
            output, receipt_path = save_export(
                image, receipt, args.output, args.input, args.overwrite
            )
            print(f"图片：{output}\n本地凭据：{receipt_path}")
            if receipt["frequency"]:
                print(f"副本编号：{receipt['frequency']['trace_id']}；导出前提取校验通过。")
                print("仅发送 PNG；请自行保留密码和 .receipt.json。")
        else:
            receipt = load_receipt(args.receipt)
            corners = list(zip(args.corners[::2], args.corners[1::2])) if args.corners else None
            result = extract_watermark(load_image(args.image), receipt, get_password(args), corners)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
