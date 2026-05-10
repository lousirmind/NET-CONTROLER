#!/usr/bin/env python3
"""生成 VibeNet Control 应用图标（1024x1024 PNG → .icns）"""

import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def create_icon_png(output_path="icon.png", size=1024):
    """绘制一个简单的网络控制图标。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 圆形背景
    margin = size // 16
    circle_bbox = [margin, margin, size - margin, size - margin]
    draw.ellipse(circle_bbox, fill=(30, 40, 55, 255))

    # Wi-Fi 弧线（三条弧）
    cx, cy = size // 2, size // 2
    arc_color = (100, 200, 255, 255)

    for i, (outer_r, inner_r, width) in enumerate([
        (cx * 0.85, cx * 0.55, size // 18),
        (cx * 0.62, cx * 0.38, size // 18),
        (cx * 0.38, cx * 0.20, size // 18),
    ]):
        # 画上半圆弧
        arc_bbox = [
            int(cx - outer_r), int(cy - outer_r),
            int(cx + outer_r), int(cy + outer_r),
        ]
        # Pillow 的 arc 绘制受限，改用 pieslice 后遮盖内部
        draw.arc(
            [int(cx - outer_r), int(cy - outer_r), int(cx + outer_r), int(cy + outer_r)],
            start=210, end=330, fill=arc_color, width=int(width),
        )

    # 底部圆点
    dot_r = size // 30
    draw.ellipse(
        [cx - dot_r, cy + cx * 0.55 - dot_r,
         cx + dot_r, cy + cx * 0.55 + dot_r],
        fill=arc_color,
    )

    # 控制滑块装饰（右下角三条横线）
    bar_x = int(cx * 1.25)
    bar_y_start = int(cy * 0.9)
    bar_color = (80, 180, 240, 255)
    for j in range(3):
        y = bar_y_start + j * size // 18
        bar_w = size // 6
        bar_h = size // 28
        draw.rounded_rectangle(
            [bar_x - bar_w // 2, y, bar_x + bar_w // 2, y + bar_h],
            radius=bar_h // 2, fill=bar_color,
        )

    img.save(output_path, "PNG")
    print(f"[*] Icon saved: {output_path}")
    return output_path


def png_to_icns(png_path, icns_path="icon.icns"):
    """将 PNG 转为 macOS .icns 格式。"""
    # 创建临时 .iconset 目录
    iconset = Path("icon.iconset")
    iconset.mkdir(exist_ok=True)

    sizes = {
        "16x16": 16, "16x16@2x": 32,
        "32x32": 32, "32x32@2x": 64,
        "128x128": 128, "128x128@2x": 256,
        "256x256": 256, "256x256@2x": 512,
        "512x512": 512, "512x512@2x": 1024,
    }

    img = Image.open(png_path)

    for name, s in sizes.items():
        resized = img.resize((s, s), Image.LANCZOS)
        resized.save(iconset / f"icon_{name}.png", "PNG")

    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", icns_path], check=True)

    # 清理
    import shutil
    shutil.rmtree(iconset, ignore_errors=True)

    print(f"[*] ICNS saved: {icns_path}")
    return icns_path


if __name__ == "__main__":
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    png_path = os.path.join(out_dir, "icon.png")
    icns_path = os.path.join(out_dir, "icon.icns")

    create_icon_png(png_path)
    png_to_icns(png_path, icns_path)
    print("[*] Icon generation complete.")
