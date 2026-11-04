"""Makes a short synthetic test video (moving blocks on a dark scene) for the screenshot and quick runs."""

from __future__ import annotations

import os
import sys

import cv2
import numpy as np


def make_video(path: str, seconds: int = 12, fps: int = 25, size=(960, 540)) -> str:
    w, h = size
    out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    rng = np.random.default_rng(3)
    stars = rng.integers(0, [w, h], size=(120, 2))
    for i in range(seconds * fps):
        img = np.full((h, w, 3), (34, 38, 44), np.uint8)
        cv2.rectangle(img, (0, int(h * 0.62)), (w, h), (46, 52, 60), -1)         # "road"
        for k in range(0, w, 80):
            cv2.line(img, (k, int(h * 0.8)), (k + 40, int(h * 0.8)), (120, 120, 120), 2)
        for sx, sy in stars:
            img[sy % (h // 2), sx % w] = (90, 90, 95)
        out.write(img)
    out.release()
    return path


if __name__ == "__main__":
    dest = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "sample.mp4")
    print(make_video(os.path.abspath(dest)))
