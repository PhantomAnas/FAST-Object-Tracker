"""The full loop with a synthetic video and a fake detector (no YOLO needed)."""

import os

import cv2
import numpy as np
import pytest

from fasttracker.counter import Track
from fasttracker.detector import ModelInfo
from fasttracker.pipeline import Callbacks, Pipeline, PipelineError
from fasttracker.settings import AlarmRule, TrackerSettings


class FakeDetector:
    """A square moves down the frame; one more object appears later."""

    def __init__(self):
        self.info = ModelInfo("fake.pt", {0: "person", 1: "car"}, False, "cpu")
        self.frame = 0

    def load(self, log=None):
        if log:
            log("fake model loaded")
        return self.info

    @property
    def names(self):
        return self.info.names

    def class_ids(self, wanted):
        return None if not wanted else [i for i, n in self.names.items() if n in wanted] or None

    def unknown_classes(self, wanted):
        return [w for w in wanted if w not in self.names.values()]

    def track(self, frame, conf, iou, imgsz, classes, max_det):
        self.frame += 1
        h, w = frame.shape[:2]
        y = 10 + self.frame * 6
        tracks = [Track(1, "person", 0.9, (w / 2 - 20, y - 20, w / 2 + 20, y + 20))]
        if self.frame > 20:
            y2 = h - 10 - (self.frame - 20) * 6
            tracks.append(Track(2, "car", 0.8, (60, y2 - 15, 120, y2 + 15)))
        return tracks


@pytest.fixture
def video(tmp_path):
    path = str(tmp_path / "in.mp4")
    w = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 25, (320, 240))
    for i in range(60):
        img = np.full((240, 320, 3), 40, np.uint8)
        cv2.putText(img, str(i), (10, 200), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        w.write(img)
    w.release()
    return path


def run(settings, det=None):
    frames, events, messages, alarms, status = [], [], [], [], []
    cb = Callbacks()
    cb.on_frame = frames.append
    cb.on_event = lambda ev, total: events.append((ev, total))
    cb.on_message = lambda lvl, txt: messages.append((lvl, txt))
    cb.on_alarm = lambda rule, count: alarms.append((rule, count))
    cb.on_status = lambda name, ok: status.append((name, ok))
    pipe = Pipeline(settings, cb, det or FakeDetector())
    stats = pipe.run()
    return stats, frames, events, messages, alarms, status


def test_pipeline_counts_crossing_and_logs(video, tmp_path):
    s = TrackerSettings(source_kind="file", file_path=video, loop_file=False, classes=["person", "car"],
                        log_folder=str(tmp_path / "logs"), output_folder=str(tmp_path / "out"),
                        alarms=[AlarmRule(cls="person", count=1, action="beep")], display_fps=1000)
    stats, frames, events, messages, alarms, status = run(s)
    assert stats.frame == 60
    assert stats.totals["person"]["in"] + stats.totals["person"]["out"] == 1
    assert stats.totals["car"]["in"] + stats.totals["car"]["out"] == 1
    assert stats.total == 2 and len(events) == 2
    assert 10 <= len(frames) <= 60 and frames[0].shape == (240, 320, 3)
    assert alarms and alarms[0][0].cls == "person"
    assert ("model", True) in status and ("source", True) in status
    logs = os.listdir(tmp_path / "logs")
    assert len(logs) == 1
    lines = open(tmp_path / "logs" / logs[0], encoding="utf-8").read().splitlines()
    assert lines[0].startswith("time,frame,track_id,class,kind,direction") and len(lines) == 3
    assert any("end of video" in m for _, m in messages)


def test_pipeline_touch_mode_and_recording(video, tmp_path):
    s = TrackerSettings(source_kind="file", file_path=video, loop_file=False, classes=[], count_cross=False,
                        count_touch=True, log_csv=False, record_video=True, output_folder=str(tmp_path / "out"),
                        snapshot_on_alarm=True, alarms=[AlarmRule(cls="*", count=2, action="sound", sound_path="")])
    stats, frames, events, messages, alarms, status = run(s)
    assert stats.totals["person"]["touch"] == 1 and stats.totals["car"]["touch"] == 1
    out = os.listdir(tmp_path / "out")
    assert any(f.endswith(".mp4") for f in out) and any(f.startswith("alarm_") for f in out)


def test_pipeline_reset_and_line_move(video, tmp_path):
    s = TrackerSettings(source_kind="file", file_path=video, loop_file=False, classes=["person"], log_csv=False)
    cb = Callbacks()
    seen = []

    pipe = Pipeline(s, cb, FakeDetector())

    def on_stats(st):
        seen.append(st.frame)
        if st.frame > 5 and len(seen) == 1:
            pipe.set_line((0.0, 0.9, 1.0, 0.9))
            pipe.reset_counts()
    cb.on_stats = on_stats
    pipe.stats_interval = 0
    stats = pipe.run()
    assert stats.frame == 60
    assert stats.total >= 1   # person reaches y=0.9*240=216 at frame ~34


def test_pipeline_stop(video):
    s = TrackerSettings(source_kind="file", file_path=video, loop_file=True, classes=["person"], log_csv=False,
                        display_fps=100000)
    cb = Callbacks()
    pipe = Pipeline(s, cb, FakeDetector())
    cb.on_frame = lambda f: pipe.stop() if pipe.stats.frame >= 10 else None
    stats = pipe.run()
    assert 10 <= stats.frame <= 12      # the video loops, so without stop() this would run forever


def test_pipeline_bad_source_raises(tmp_path):
    s = TrackerSettings(source_kind="file", file_path=str(tmp_path / "missing.mp4"))
    with pytest.raises(PipelineError):
        Pipeline(s, Callbacks(), FakeDetector()).run()
    s = TrackerSettings(source_kind="url", url="")
    with pytest.raises(PipelineError):
        Pipeline(s, Callbacks(), FakeDetector()).run()


def test_pipeline_unknown_class_warns(video):
    s = TrackerSettings(source_kind="file", file_path=video, loop_file=False, classes=["dragon"], log_csv=False)
    stats, frames, events, messages, alarms, status = run(s)
    assert any("dragon" in m for _, m in messages)
    assert stats.total == 2      # falls back to counting every class
