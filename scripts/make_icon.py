"""Draws assets/icon.png and assets/icon.ico: a dark rounded square with a teal target + line."""

from __future__ import annotations

import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")


def draw(size: int) -> Image.Image:
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = s * 0.22
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=r, fill=(26, 29, 34, 255))
    d.rounded_rectangle((s * 0.03, s * 0.03, s * 0.97, s * 0.97), radius=r * 0.9, outline=(255, 255, 255, 28), width=max(1, s // 64))
    teal = (45, 212, 191, 255)
    c = s / 2
    lw = max(2, int(s * 0.06))
    for rad in (0.36, 0.22):
        d.ellipse((c - s * rad, c - s * rad, c + s * rad, c + s * rad), outline=teal, width=lw)
    d.ellipse((c - s * 0.07, c - s * 0.07, c + s * 0.07, c + s * 0.07), fill=teal)
    # the counting line across
    d.line((s * 0.08, c, s * 0.92, c), fill=(230, 232, 236, 230), width=max(2, int(s * 0.045)))
    for x in (s * 0.08, s * 0.92):
        d.ellipse((x - s * 0.05, c - s * 0.05, x + s * 0.05, c + s * 0.05), fill=(230, 232, 236, 255))
    return img


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    big = draw(512)
    big.save(os.path.join(OUT, "icon.png"))
    big.save(os.path.join(OUT, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", OUT)


if __name__ == "__main__":
    main()
