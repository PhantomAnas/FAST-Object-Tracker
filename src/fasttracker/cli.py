"""Command line: `python -m fasttracker --cli --source video.mp4 --classes person,car`."""

from __future__ import annotations

import argparse
import os
import sys
import threading

from . import __version__
from .settings import KNOWN_MODELS, AlarmRule, TrackerSettings, config_path
from .source import STREAM_PREFIXES, VIDEO_EXTENSIONS


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fasttracker", description="FAST Object Tracker - count objects crossing or touching a line.")
    p.add_argument("--version", action="version", version=f"FAST Object Tracker {__version__}")
    src = p.add_argument_group("source")
    src.add_argument("--source", help="webcam index (0, 1...), a video file, or a stream URL (rtsp://..., http://...)")
    src.add_argument("--no-loop", action="store_true", help="do not loop a video file")
    mdl = p.add_argument_group("model")
    mdl.add_argument("--model", help="base model name (" + ", ".join(KNOWN_MODELS) + ") or a path to your .pt")
    mdl.add_argument("--class-names", help="comma list renaming a custom model's classes")
    mdl.add_argument("--classes", help="comma list of classes to count (default: person; 'all' = every class)")
    mdl.add_argument("--conf", type=float)
    mdl.add_argument("--iou", type=float)
    mdl.add_argument("--imgsz", type=int)
    mdl.add_argument("--device", choices=("auto", "cpu", "cuda"))
    mdl.add_argument("--tracker", choices=("bytetrack", "botsort"))
    mdl.add_argument("--detect-every", type=int, help="run the model every Nth frame")
    ln = p.add_argument_group("counting line")
    ln.add_argument("--line", help="x1,y1,x2,y2 as fractions of the frame, e.g. 0.1,0.5,0.9,0.5")
    ln.add_argument("--cross", choices=("on", "off"), help="count when the object's centre crosses the line")
    ln.add_argument("--touch", choices=("on", "off"), help="count when the object's box touches the line")
    ln.add_argument("--direction", choices=("both", "in", "out"))
    al = p.add_argument_group("alarms and serial")
    al.add_argument("--alarm", action="append", default=[], metavar="CLASS:COUNT[:ACTION][:repeat]",
                    help="e.g. person:10:beep or car:50:serial:repeat (may repeat the option)")
    al.add_argument("--beep-on-count", action="store_true")
    al.add_argument("--serial", action="store_true", help="send a serial message to an Arduino on each count")
    al.add_argument("--serial-port", help="COM3, /dev/ttyUSB0... (default: auto-detect)")
    al.add_argument("--serial-baud", type=int)
    al.add_argument("--serial-message", help=r"text to send, escapes allowed (default 'Go\r')")
    al.add_argument("--serial-on", choices=("count", "alarm", "never"))
    out = p.add_argument_group("output")
    out.add_argument("--record", action="store_true", help="record the annotated video")
    out.add_argument("--no-log", action="store_true", help="do not write the CSV log")
    out.add_argument("--output", help="folder for recordings and snapshots")
    out.add_argument("--show", action="store_true", help="show a live window (press q to stop)")
    out.add_argument("--max-frames", type=int, default=0, help="stop after N frames (0 = run until the end)")
    p.add_argument("--save-settings", action="store_true", help="save these options as the GUI defaults")
    p.add_argument("--list-ports", action="store_true", help="list serial ports and exit")
    p.add_argument("--list-webcams", action="store_true", help="list working webcam indices and exit")
    return p


def parse_alarm(text: str) -> AlarmRule:
    parts = text.split(":")
    if len(parts) < 2:
        raise ValueError(f"alarm '{text}' must look like CLASS:COUNT[:ACTION][:repeat]")
    rule = AlarmRule(cls=parts[0].strip() or "*", count=int(parts[1]))
    if len(parts) > 2 and parts[2]:
        rule.action = parts[2].strip()
    rule.repeat = "repeat" in [x.strip().lower() for x in parts[3:]]
    return rule


def apply_args(s: TrackerSettings, a: argparse.Namespace) -> TrackerSettings:
    if a.source is not None:
        src = a.source.strip()
        if src.isdigit():
            s.source_kind, s.webcam_index = "webcam", int(src)
        elif os.path.isfile(src) or (not src.lower().startswith(STREAM_PREFIXES) and
                                      (os.path.splitext(src)[1].lower() in VIDEO_EXTENSIONS or os.sep in src)):
            s.source_kind, s.file_path = "file", src
        else:
            s.source_kind, s.url = "url", src
    if a.no_loop:
        s.loop_file = False
    if a.model:
        s.model = a.model
    if a.class_names is not None:
        s.class_names = a.class_names
    if a.classes is not None:
        s.classes = [] if a.classes.strip().lower() == "all" else [c.strip() for c in a.classes.split(",") if c.strip()]
    for name in ("conf", "iou", "imgsz", "device", "tracker", "detect_every", "direction", "serial_port", "serial_baud",
                 "serial_message", "serial_on"):
        v = getattr(a, name, None)
        if v is not None:
            setattr(s, name, v)
    if a.line:
        vals = [float(x) for x in a.line.split(",")]
        if len(vals) != 4:
            raise ValueError("--line needs four numbers")
        s.line = tuple(vals)  # type: ignore[assignment]
    if a.cross:
        s.count_cross = a.cross == "on"
    if a.touch:
        s.count_touch = a.touch == "on"
    if a.alarm:
        s.alarms = [parse_alarm(t) for t in a.alarm]
    if a.beep_on_count:
        s.beep_on_count = True
    if a.serial:
        s.serial_enabled = True
    if a.record:
        s.record_video = True
    if a.no_log:
        s.log_csv = False
    if a.output:
        s.output_folder = a.output
    return s


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    if a.list_ports:
        from .serial_link import list_ports
        ports = list_ports()
        print("\n".join(f"{d}\t{desc}" for d, desc in ports) if ports else "no serial ports found")
        return 0
    if a.list_webcams:
        from .source import list_webcams
        cams = list_webcams()
        print("webcams: " + (", ".join(map(str, cams)) if cams else "none found"))
        return 0
    s = TrackerSettings.load()
    try:
        apply_args(s, a)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if a.save_settings:
        s.save()
        print(f"settings saved to {config_path()}")
        if a.source is None:
            return 0
    problems = s.validate()
    if problems:
        print("error: " + "; ".join(problems), file=sys.stderr)
        return 2

    from .pipeline import Callbacks, Pipeline, PipelineError

    show = a.show
    stop_flag = threading.Event()

    def on_frame(frame):
        if not show:
            return
        import cv2
        cv2.imshow("FAST Object Tracker (q = stop)", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            stop_flag.set()

    def on_event(ev, total):
        print(f"[count] #{ev.track_id} {ev.name} {ev.kind} {ev.direction}  total {total}")

    def on_message(level, text):
        print(f"[{level}] {text}")

    cb = Callbacks()
    cb.on_frame = on_frame
    cb.on_event = on_event
    cb.on_message = on_message
    cb.on_alarm = lambda rule, count: print(f"[alarm] {rule.describe()} at {count}")
    pipe = Pipeline(s, cb)
    if a.max_frames or show:
        def watch():
            import time
            while not stop_flag.is_set():
                if a.max_frames and pipe.stats.frame >= a.max_frames:
                    break
                time.sleep(0.1)
            pipe.stop()
        threading.Thread(target=watch, daemon=True).start()
    try:
        stats = pipe.run()
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pipe.stop()
        print("\nstopped")
        return 130
    finally:
        if show:
            try:
                import cv2
                cv2.destroyAllWindows()
            except Exception:  # noqa: BLE001
                pass
    for name, v in sorted(stats.totals.items()):
        print(f"{name}: {sum(v.values())}  (in {v['in']}, out {v['out']}, touch {v['touch']})")
    print(f"total: {stats.total}")
    return 0
