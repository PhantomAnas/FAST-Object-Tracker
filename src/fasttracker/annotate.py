"""Drawing on frames: boxes, ids, trails, the counting line and the counts panel."""

from __future__ import annotations

from collections import defaultdict, deque

import cv2
import numpy as np

from .counter import Totals, Track

# A restrained palette; the class id picks the colour.
PALETTE = [(66, 133, 244), (52, 199, 89), (255, 159, 10), (191, 90, 242), (255, 69, 58), (48, 209, 255),
           (255, 214, 10), (172, 142, 104), (100, 210, 255), (255, 105, 180)]
LINE_COLOR = (191, 212, 45)      # BGR teal (matches the app accent)
FLASH_COLOR = (255, 255, 255)


def color_for(name: str) -> tuple[int, int, int]:
    r, g, b = PALETTE[sum(map(ord, name)) % len(PALETTE)]
    return (b, g, r)


class Trails:
    def __init__(self, length: int = 40) -> None:
        self.length = max(2, length)
        self._pts: dict[int, deque] = defaultdict(lambda: deque(maxlen=self.length))
        self._seen: dict[int, int] = {}

    def update(self, tracks: list[Track], frame: int) -> None:
        for t in tracks:
            self._pts[t.id].append(tuple(int(v) for v in t.center))
            self._seen[t.id] = frame
        for tid in [tid for tid, f in self._seen.items() if frame - f > 60]:
            self._pts.pop(tid, None)
            self._seen.pop(tid, None)

    def draw(self, img: np.ndarray, tracks: list[Track]) -> None:
        for t in tracks:
            pts = self._pts.get(t.id)
            if pts and len(pts) > 1:
                cv2.polylines(img, [np.array(pts, dtype=np.int32)], False, color_for(t.name), 2, cv2.LINE_AA)

    def clear(self) -> None:
        self._pts.clear()
        self._seen.clear()


def draw_tracks(img: np.ndarray, tracks: list[Track], show_labels: bool = True, show_conf: bool = False,
                highlight: set[int] | None = None) -> None:
    for t in tracks:
        x1, y1, x2, y2 = (int(v) for v in t.xyxy)
        color = color_for(t.name)
        thick = 3 if highlight and t.id in highlight else 2
        cv2.rectangle(img, (x1, y1), (x2, y2), color, thick, cv2.LINE_AA)
        if show_labels:
            label = f"{t.name} #{t.id}" + (f" {t.conf:.2f}" if show_conf else "")
            (tw, th), base = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(img, (x1, max(0, y1 - th - base - 6)), (x1 + tw + 8, y1), color, -1)
            cv2.putText(img, label, (x1 + 4, max(th + 2, y1 - base - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)


def draw_line(img: np.ndarray, a: tuple[float, float], b: tuple[float, float], flash: bool = False,
              label_sides: bool = True) -> None:
    ax, ay, bx, by = int(a[0]), int(a[1]), int(b[0]), int(b[1])
    color = FLASH_COLOR if flash else LINE_COLOR
    cv2.line(img, (ax, ay), (bx, by), (0, 0, 0), 5, cv2.LINE_AA)
    cv2.line(img, (ax, ay), (bx, by), color, 3 if flash else 2, cv2.LINE_AA)
    for x, y in ((ax, ay), (bx, by)):
        cv2.circle(img, (x, y), 6, color, -1, cv2.LINE_AA)
        cv2.circle(img, (x, y), 6, (0, 0, 0), 1, cv2.LINE_AA)
    if label_sides:
        # "IN" is the left side of a->b; put small arrows at the midpoint.
        mx, my = (ax + bx) / 2, (ay + by) / 2
        dx, dy = bx - ax, by - ay
        n = (dx * dx + dy * dy) ** 0.5 or 1.0
        nx, ny = -dy / n, dx / n          # normal pointing to the left of a->b (image coords: y down)
        for sign, text in ((-1, "IN"), (1, "OUT")):
            px, py = int(mx + sign * nx * 22), int(my + sign * ny * 22)
            cv2.putText(img, text, (px - 12, py + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(img, text, (px - 12, py + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)


def draw_panel(img: np.ndarray, totals: Totals, fps: float, extra: str = "") -> None:
    rows = [f"{name}: {v['in'] + v['out'] + v['touch']}  (in {v['in']}  out {v['out']}  touch {v['touch']})"
            for name, v in sorted(totals.as_dict().items())]
    head = f"TOTAL {totals.total()}    {fps:.1f} fps" + (f"    {extra}" if extra else "")
    lines = [head] + rows[:10]
    w = max(cv2.getTextSize(ln, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)[0][0] for ln in lines) + 20
    h = 14 + 22 * len(lines)
    overlay = img.copy()
    cv2.rectangle(overlay, (10, 10), (10 + w, 10 + h), (20, 22, 28), -1)
    cv2.addWeighted(overlay, 0.75, img, 0.25, 0, img)
    y = 30
    for i, ln in enumerate(lines):
        cv2.putText(img, ln, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255) if i else (120, 220, 255), 1, cv2.LINE_AA)
        y += 22
