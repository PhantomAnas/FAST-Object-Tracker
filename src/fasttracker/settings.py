"""Tracker settings and their JSON persistence."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields

from platformdirs import user_config_dir, user_data_dir

APP_NAME = "FASTObjectTracker"

SOURCE_KINDS = ("webcam", "file", "url")
DIRECTIONS = ("both", "in", "out")
DEVICES = ("auto", "cpu", "cuda")
TRACKERS = ("bytetrack", "botsort")
ALARM_ACTIONS = ("beep", "sound", "serial", "beep+serial")
SERIAL_ON = ("count", "alarm", "never")

# Base YOLO models that download from the official Ultralytics release on first use.
KNOWN_MODELS: dict[str, str] = {
    "yolo11n.pt": "YOLO11 nano (fastest, default)",
    "yolo11s.pt": "YOLO11 small (more accurate)",
    "yolo11m.pt": "YOLO11 medium (slow on CPU)",
    "yolov8n.pt": "YOLOv8 nano",
    "yolov8s.pt": "YOLOv8 small",
}


def config_path() -> str:
    return os.path.join(user_config_dir(APP_NAME, appauthor=False), "settings.json")


def data_dir() -> str:
    return user_data_dir(APP_NAME, appauthor=False)


@dataclass
class AlarmRule:
    cls: str = "person"          # class name, or "*" for the total of all counted classes
    count: int = 10
    action: str = "beep"         # beep | sound | serial | beep+serial
    sound_path: str = ""
    repeat: bool = False         # fire again every `count` more objects
    enabled: bool = True

    def describe(self) -> str:
        what = "any object" if self.cls == "*" else self.cls
        every = f"every {self.count}" if self.repeat else f"at {self.count}"
        return f"{what} {every}: {self.action}"


@dataclass
class TrackerSettings:
    # Source
    source_kind: str = "webcam"          # webcam | file | url
    webcam_index: int = 0
    file_path: str = ""
    url: str = ""                        # rtsp://user:pass@ip:554/..., http://... (ip cameras, CCTV)
    loop_file: bool = True
    reconnect: bool = True               # for streams: retry when the link drops

    # Model
    model: str = "yolo11n.pt"            # a known base model, or a path to your own .pt
    class_names: str = ""                # optional comma list that renames a custom model's classes
    classes: list[str] = field(default_factory=lambda: ["person"])   # empty = every class
    conf: float = 0.4
    iou: float = 0.5
    imgsz: int = 640
    device: str = "auto"                 # auto | cpu | cuda
    tracker: str = "bytetrack"
    detect_every: int = 1                # run the model every Nth frame (tracks are held in between)
    max_det: int = 100

    # Counting line (normalised 0..1 of the frame)
    line: tuple[float, float, float, float] = (0.1, 0.5, 0.9, 0.5)
    count_cross: bool = True
    count_touch: bool = False
    direction: str = "both"              # both | in | out
    min_track_frames: int = 2            # an id must be seen this many frames before it can count

    # Display
    show_trails: bool = True
    trail_length: int = 40
    show_labels: bool = True
    show_conf: bool = False
    display_fps: int = 30

    # Alarms
    alarms: list[AlarmRule] = field(default_factory=list)
    beep_on_count: bool = False

    # Serial / Arduino
    serial_enabled: bool = False
    serial_port: str = ""                # empty = first USB serial device found
    serial_baud: int = 9600
    serial_message: str = "Go\\r"        # escapes like \r \n are interpreted
    serial_on: str = "count"             # count | alarm | never
    serial_classes: list[str] = field(default_factory=list)   # empty = the counted classes

    # Output
    log_csv: bool = True
    log_folder: str = ""
    record_video: bool = False
    snapshot_on_alarm: bool = False
    output_folder: str = ""
    extra: dict = field(default_factory=dict)

    # ------------------------------------------------------------ helpers
    def validate(self) -> list[str]:
        problems = []
        if self.source_kind not in SOURCE_KINDS:
            problems.append(f"unknown source kind '{self.source_kind}'")
        if self.source_kind == "file" and not os.path.isfile(self.file_path):
            problems.append("video file does not exist")
        if self.source_kind == "url" and not self.url.strip():
            problems.append("stream URL is empty")
        if self.source_kind == "webcam" and self.webcam_index < 0:
            problems.append("webcam index must be 0 or more")
        if not self.model:
            problems.append("no model chosen")
        elif self.model not in KNOWN_MODELS and not os.path.isfile(self.model):
            problems.append(f"model file not found: {self.model}")
        if not 0.01 <= self.conf <= 0.99:
            problems.append("confidence must be between 0.01 and 0.99")
        if not 0.1 <= self.iou <= 0.95:
            problems.append("IoU must be between 0.1 and 0.95")
        if self.imgsz < 32 or self.imgsz % 32:
            problems.append("image size must be a multiple of 32")
        if self.device not in DEVICES:
            problems.append(f"unknown device '{self.device}'")
        if self.tracker not in TRACKERS:
            problems.append(f"unknown tracker '{self.tracker}'")
        if self.detect_every < 1:
            problems.append("detect every N frames must be at least 1")
        if len(self.line) != 4 or not all(0.0 <= float(v) <= 1.0 for v in self.line):
            problems.append("line must be four values between 0 and 1")
        if not (self.count_cross or self.count_touch):
            problems.append("enable at least one of 'count on cross' and 'count on touch'")
        if self.direction not in DIRECTIONS:
            problems.append(f"unknown direction '{self.direction}'")
        if self.serial_on not in SERIAL_ON:
            problems.append(f"unknown serial trigger '{self.serial_on}'")
        if self.serial_baud <= 0:
            problems.append("baud rate must be positive")
        for i, rule in enumerate(self.alarms, start=1):
            if rule.count < 1:
                problems.append(f"alarm {i}: count must be at least 1")
            if rule.action not in ALARM_ACTIONS:
                problems.append(f"alarm {i}: unknown action '{rule.action}'")
            if rule.action == "sound" and rule.sound_path and not os.path.isfile(rule.sound_path):
                problems.append(f"alarm {i}: sound file not found")
        return problems

    @property
    def serial_bytes(self) -> bytes:
        return self.serial_message.encode("utf-8").decode("unicode_escape").encode("latin-1", "replace")

    def default_output_folder(self) -> str:
        return self.output_folder or os.path.join(os.path.expanduser("~"), "Videos", "FAST Object Tracker")

    def default_log_folder(self) -> str:
        return self.log_folder or os.path.join(data_dir(), "logs")

    # -------------------------------------------------------- persistence
    @classmethod
    def from_dict(cls, data: dict) -> "TrackerSettings":
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in data.items() if k in known}
        if "line" in clean:
            try:
                clean["line"] = tuple(max(0.0, min(1.0, float(v))) for v in clean["line"][:4])
                if len(clean["line"]) != 4:
                    clean.pop("line")
            except (TypeError, ValueError):
                clean.pop("line")
        rule_fields = {f.name for f in fields(AlarmRule)}
        rules = []
        for r in clean.get("alarms", []) or []:
            if isinstance(r, dict):
                try:
                    rules.append(AlarmRule(**{k: v for k, v in r.items() if k in rule_fields}))
                except TypeError:
                    continue
        clean["alarms"] = rules
        for key in ("classes", "serial_classes"):
            if key in clean and not isinstance(clean[key], list):
                clean.pop(key)
        try:
            return cls(**clean)
        except TypeError:
            return cls()

    @classmethod
    def load(cls, path: str | None = None) -> "TrackerSettings":
        path = path or config_path()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return cls()
        return cls.from_dict(data) if isinstance(data, dict) else cls()

    def save(self, path: str | None = None) -> None:
        path = path or config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, indent=2)
        os.replace(tmp, path)
