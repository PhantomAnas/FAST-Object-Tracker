"""The processing loop: source -> detector/tracker -> line counter -> alarms,
serial, log, recording -> annotated frame.  Runs on a worker thread; the GUI
and the CLI both drive it through callbacks."""

from __future__ import annotations

import csv
import datetime as dt
import os
import threading
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import alarms as alarmmod
from .annotate import Trails, draw_line, draw_panel, draw_tracks
from .counter import CountEvent, LineCounter, Track
from .detector import Detector, DetectorError
from .serial_link import SerialError, SerialLink
from .settings import AlarmRule, TrackerSettings
from .source import SourceError, VideoSource, describe_source


class PipelineError(Exception):
    pass


@dataclass
class Stats:
    frame: int = 0
    fps: float = 0.0
    infer_ms: float = 0.0
    totals: dict = field(default_factory=dict)
    total: int = 0
    tracked: int = 0
    width: int = 0
    height: int = 0
    serial_open: bool = False
    serial_sent: int = 0
    source_ok: bool = True


@dataclass
class Callbacks:
    on_frame=None          # (bgr ndarray)
    on_stats=None          # (Stats)
    on_event=None          # (CountEvent, total)
    on_message=None        # (level, text)  level: info | warn | error | ok
    on_alarm=None          # (AlarmRule, count)
    on_status=None         # (name, bool)  name: source | model | serial


class Pipeline:
    def __init__(self, settings: TrackerSettings, callbacks: Callbacks, detector: Detector | None = None) -> None:
        self.s = settings
        self.cb = callbacks
        self.detector = detector
        self._stop = threading.Event()
        self._line_lock = threading.Lock()
        self._line = tuple(settings.line)
        self._line_dirty = False
        self._reset_requested = False
        self._snapshot_requested = False
        self.counter: LineCounter | None = None
        self.serial: SerialLink | None = None
        self.stats = Stats()
        self.stats_interval = 0.5
        self.error = ""          # set when the loop ended because of a failure

    # ------------------------------------------------------------ control
    def stop(self) -> None:
        self._stop.set()

    def set_line(self, line: tuple[float, float, float, float]) -> None:
        with self._line_lock:
            self._line = tuple(line)
            self._line_dirty = True

    def reset_counts(self) -> None:
        self._reset_requested = True

    def snapshot(self) -> None:
        self._snapshot_requested = True

    # ------------------------------------------------------------ helpers
    def _say(self, level: str, text: str) -> None:
        if self.cb.on_message:
            self.cb.on_message(level, text)

    def _status(self, name: str, ok: bool) -> None:
        if self.cb.on_status:
            self.cb.on_status(name, ok)

    def _line_px(self, w: int, h: int) -> tuple[tuple[float, float], tuple[float, float]]:
        with self._line_lock:
            x1, y1, x2, y2 = self._line
        return (x1 * w, y1 * h), (x2 * w, y2 * h)

    # --------------------------------------------------------------- run
    def run(self) -> Stats:
        s = self.s
        problems = s.validate()
        if problems:
            raise PipelineError("; ".join(problems))

        # Source
        self._say("info", f"opening {describe_source(s)}...")
        try:
            src = VideoSource(s).open()
        except SourceError as exc:
            self._status("source", False)
            raise PipelineError(str(exc)) from exc
        self._status("source", True)
        self._say("ok", f"source ready: {src.width}x{src.height}" + (f" @ {src.fps:.0f} fps" if src.fps else ""))

        # Model
        det = self.detector or Detector(s.model, s.device, s.class_names, s.tracker)
        try:
            det.load(lambda m: self._say("info", m))
        except DetectorError as exc:
            src.release()
            self._status("model", False)
            raise PipelineError(str(exc)) from exc
        self._status("model", True)
        class_ids = det.class_ids(s.classes)
        unknown = det.unknown_classes(s.classes)
        if unknown:
            self._say("warn", "classes not in this model and ignored: " + ", ".join(unknown))
        if s.classes and class_ids is None:
            self._say("warn", "none of the chosen classes exist in this model; counting every class")

        # Serial
        self.serial = None
        if s.serial_enabled:
            self.serial = SerialLink(s.serial_port, s.serial_baud, s.serial_bytes)
            try:
                port = self.serial.open()
                self._status("serial", True)
                self._say("ok", f"serial open on {port} @ {s.serial_baud}")
            except SerialError as exc:
                self._status("serial", False)
                self._say("warn", f"serial: {exc} (will keep trying)")
        serial_classes = {c.lower() for c in (s.serial_classes or s.classes)}

        # Outputs
        log_fh = None
        log_writer = None
        if s.log_csv:
            try:
                folder = s.default_log_folder()
                os.makedirs(folder, exist_ok=True)
                log_path = os.path.join(folder, dt.datetime.now().strftime("counts_%Y-%m-%d_%H%M%S.csv"))
                log_fh = open(log_path, "w", newline="", encoding="utf-8")
                log_writer = csv.writer(log_fh)
                log_writer.writerow(["time", "frame", "track_id", "class", "kind", "direction", "class_total", "total"])
                self._say("info", f"logging counts to {log_path}")
            except OSError as exc:
                self._say("warn", f"could not open the CSV log: {exc}")
        writer = None
        if s.record_video:
            try:
                folder = s.default_output_folder()
                os.makedirs(folder, exist_ok=True)
                rec_path = os.path.join(folder, dt.datetime.now().strftime("tracking_%Y-%m-%d_%H%M%S.mp4"))
                fps = src.fps if 1 <= src.fps <= 60 else 25.0
                writer = cv2.VideoWriter(rec_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (src.width, src.height))
                if not writer.isOpened():
                    writer = None
                    self._say("warn", "could not start the video recording")
                else:
                    self._say("info", f"recording to {rec_path}")
            except Exception as exc:  # noqa: BLE001
                writer = None
                self._say("warn", f"recording disabled: {exc}")

        a, b = self._line_px(src.width or 1, src.height or 1)
        self.counter = LineCounter(a, b, s.count_cross, s.count_touch, s.direction, s.min_track_frames)
        alarms = alarmmod.AlarmEngine(s.alarms)
        trails = Trails(s.trail_length)
        tracks: list[Track] = []
        frame_index = 0
        t_fps = time.time()
        fps_frames = 0
        fps = 0.0
        infer_ms = 0.0
        flash_until = 0.0
        last_display = 0.0
        display_interval = 1.0 / max(1, s.display_fps)
        last_stats = 0.0
        self._say("ok", "tracking started" + (" (press Stop to end)" if not src.is_file else ""))
        try:
            while not self._stop.is_set():
                frame = src.read()
                if frame is None:
                    if src.is_file:
                        self._say("info", "end of video")
                        break
                    self._status("source", False)
                    if not s.reconnect:
                        self.error = "the source stopped delivering frames"
                        self._say("error", self.error)
                        break
                    self._say("warn", "source lost; reconnecting...")
                    if src.reconnect():
                        self._status("source", True)
                        self._say("ok", "source reconnected")
                        continue
                    if src.reconnects >= 20:
                        self.error = "could not reconnect after 20 attempts"
                        self._say("error", self.error)
                        break
                    continue
                frame_index += 1
                h, w = frame.shape[:2]
                if self._line_dirty:
                    self._line_dirty = False
                    self.counter.set_line(*self._line_px(w, h))
                if self._reset_requested:
                    self._reset_requested = False
                    self.counter.reset()
                    alarms.reset()
                    trails.clear()
                    self._say("info", "counts reset")

                # Detect / track
                if frame_index % s.detect_every == 1 or s.detect_every == 1:
                    t0 = time.time()
                    try:
                        tracks = det.track(frame, s.conf, s.iou, s.imgsz, class_ids, s.max_det)
                    except DetectorError as exc:
                        self.error = str(exc)
                        self._say("error", str(exc))
                        break
                    infer_ms = (time.time() - t0) * 1000
                events = self.counter.update(tracks, frame_index)
                trails.update(tracks, frame_index)

                # Events -> alarms / serial / log
                for ev in events:
                    flash_until = time.time() + 0.12
                    if self.cb.on_event:
                        self.cb.on_event(ev, self.counter.totals.total())
                    if log_writer:
                        log_writer.writerow([dt.datetime.fromtimestamp(ev.timestamp).isoformat(timespec="milliseconds"),
                                             ev.frame, ev.track_id, ev.name, ev.kind, ev.direction,
                                             self.counter.totals.total(ev.name), self.counter.totals.total()])
                    if s.beep_on_count:
                        alarmmod.beep(900, 80)
                    if self.serial is not None and s.serial_on == "count" and (not serial_classes or ev.name.lower() in serial_classes):
                        self._send_serial()
                for rule, count in alarms.check(self.counter.totals):
                    self._fire_alarm(rule, count, frame)
                if events and log_fh:
                    log_fh.flush()

                # Draw
                if s.show_trails:
                    trails.draw(frame, tracks)
                draw_tracks(frame, tracks, s.show_labels, s.show_conf, {e.track_id for e in events} or None)
                draw_line(frame, self.counter.a, self.counter.b, flash=time.time() < flash_until)
                draw_panel(frame, self.counter.totals, fps)
                if writer is not None:
                    writer.write(frame)
                if self._snapshot_requested:
                    self._snapshot_requested = False
                    self._save_snapshot(frame, "snapshot")

                # Stats / display
                self.stats.frame = frame_index
                fps_frames += 1
                now = time.time()
                if now - t_fps >= 1.0:
                    fps = fps_frames / (now - t_fps)
                    fps_frames, t_fps = 0, now
                if self.cb.on_frame and now - last_display >= display_interval:
                    last_display = now
                    self.cb.on_frame(frame)
                if self.cb.on_stats and now - last_stats >= self.stats_interval:
                    last_stats = now
                    self.stats = Stats(frame_index, fps, infer_ms, self.counter.totals.as_dict(), self.counter.totals.total(),
                                       len(tracks), w, h, bool(self.serial and self.serial.is_open),
                                       self.serial.sent if self.serial else 0, True)
                    self.cb.on_stats(self.stats)
                if self.serial is not None and not self.serial.is_open and self.serial.try_reconnect():
                    self._status("serial", True)
                    self._say("ok", f"serial reconnected on {self.serial.port}")
        finally:
            src.release()
            if writer is not None:
                writer.release()
            if log_fh:
                log_fh.close()
            if self.serial is not None:
                self.serial.close()
            self._status("source", False)
            self._status("serial", False)
        self.stats = Stats(frame_index, fps, infer_ms, self.counter.totals.as_dict(), self.counter.totals.total(),
                           len(tracks), src.width, src.height, False, self.serial.sent if self.serial else 0, False)
        self._say("info", f"stopped after {frame_index} frames: total {self.counter.totals.total()}")
        return self.stats

    def _send_serial(self) -> None:
        assert self.serial is not None
        if not self.serial.pulse():
            self._status("serial", False)
            if self.serial.last_error:
                self._say("warn", f"serial write failed: {self.serial.last_error}")
                self.serial.last_error = ""

    def _fire_alarm(self, rule: AlarmRule, count: int, frame: np.ndarray) -> None:
        self._say("warn", f"ALARM: {rule.describe()} (count {count})")
        if rule.action in ("beep", "beep+serial"):
            alarmmod.beep()
        elif rule.action == "sound":
            if not alarmmod.play_sound(rule.sound_path):
                self._say("warn", "alarm sound could not be played; beeped instead")
        if rule.action in ("serial", "beep+serial") or self.s.serial_on == "alarm":
            if self.serial is not None:
                self._send_serial()
        if self.s.snapshot_on_alarm:
            self._save_snapshot(frame, "alarm")
        if self.cb.on_alarm:
            self.cb.on_alarm(rule, count)

    def _save_snapshot(self, frame: np.ndarray, prefix: str) -> None:
        try:
            folder = self.s.default_output_folder()
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, dt.datetime.now().strftime(f"{prefix}_%Y-%m-%d_%H%M%S_%f.jpg"))
            cv2.imwrite(path, frame)
            self._say("info", f"saved {path}")
        except Exception as exc:  # noqa: BLE001
            self._say("warn", f"snapshot failed: {exc}")
