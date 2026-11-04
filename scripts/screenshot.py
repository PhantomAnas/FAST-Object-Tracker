"""Renders docs/screenshot.png: the real window on a synthetic video, with a
scripted detector so the shot is reproducible without a camera or weights."""

from __future__ import annotations

import math
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import fasttracker.pipeline as pl  # noqa: E402
from fasttracker.counter import Track  # noqa: E402
from fasttracker.detector import ModelInfo  # noqa: E402
from fasttracker.settings import AlarmRule, TrackerSettings  # noqa: E402
from make_samples import make_video  # noqa: E402


class ScriptedDetector:
    """People walk down across the line, cars drive along the road."""

    def __init__(self, *a, **k):
        self.info = ModelInfo("yolo11n.pt", {0: "person", 2: "car", 7: "truck"}, False, "cpu")
        self.n = 0

    def load(self, log=None):
        if log:
            log("model ready: 80 classes, device cpu")
        return self.info

    @property
    def names(self):
        return self.info.names

    def class_ids(self, wanted):
        return [i for i, n in self.names.items() if n in wanted] or None

    def unknown_classes(self, wanted):
        return [x for x in wanted if x not in self.names.values()]

    def track(self, frame, *a, **k):
        import cv2
        self.n += 1
        h, w = frame.shape[:2]
        tracks = []
        for pid, (x0, speed, start) in enumerate([(0.18, 3.2, 0), (0.42, 2.4, 40), (0.70, 2.8, 90), (0.55, 3.0, 150)], start=1):
            t = self.n - start
            if t < 0:
                continue
            period = h + 160
            cycle, phase = divmod(t * speed, period)
            y = phase - 80
            cx = x0 * w + 10 * math.sin(t / 9)
            box = (cx - 28, y - 70, cx + 28, y + 70)
            cv2.rectangle(frame, (int(box[0]) + 6, int(box[1]) + 6), (int(box[2]) - 6, int(box[3]) - 6), (74, 86, 104), -1)
            cv2.circle(frame, (int(cx), int(y - 48)), 14, (120, 134, 152), -1)
            tracks.append(Track(pid + 10 * int(cycle), "person", 0.88, box))
        for cid, (start, speed, lane, name) in enumerate([(10, 7.0, 0.66, "car"), (120, 6.0, 0.80, "truck")], start=20):
            t = self.n - start
            if t < 0:
                continue
            period = w + 260
            cycle, phase = divmod(t * speed, period)
            x = phase - 130
            y = lane * h - 0.14 * h * math.sin(t / 30)
            box = (x - 70, y - 26, x + 70, y + 26)
            cv2.rectangle(frame, (int(box[0]) + 4, int(box[1]) + 8), (int(box[2]) - 4, int(box[3]) - 4), (96, 110, 128), -1)
            tracks.append(Track(cid + 10 * int(cycle), name, 0.91, box))
        return tracks

    def reset_tracker(self):
        pass


def main() -> int:
    pl.Detector = ScriptedDetector
    tmp = tempfile.mkdtemp(prefix="fot-shot-")
    video = make_video(os.path.join(tmp, "sample.mp4"))
    import fasttracker.settings as settings_mod
    settings_mod.config_path = lambda: os.path.join(tmp, "settings.json")
    s = TrackerSettings(source_kind="file", file_path=video, classes=["person", "car", "truck"], line=(0.08, 0.55, 0.92, 0.55),
                        count_cross=True, count_touch=False, log_folder=os.path.join(tmp, "logs"),
                        output_folder=os.path.join(tmp, "out"), alarms=[AlarmRule("person", 5, "beep"), AlarmRule("*", 20, "serial", repeat=True)],
                        serial_enabled=False, display_fps=30)
    s.save()
    from fasttracker.app import theme
    from fasttracker.app.main_window import MainWindow
    app = QApplication(sys.argv)
    app.setStyleSheet(theme.STYLESHEET)
    win = MainWindow()
    win.resize(1380, 860)
    win.show()
    QTimer.singleShot(600, win.start)

    def shot():
        out = os.path.join(ROOT, "docs", "screenshot.png")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        win.grab().save(out)
        print("wrote", out)
        win.stop()
        QTimer.singleShot(1500, app.quit)
    QTimer.singleShot(9000, shot)
    app.exec()
    return 0


if __name__ == "__main__":
    sys.exit(main())
