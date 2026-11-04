# FAST Object Tracker

**Count people, vehicles, products or any object that crosses or touches a line, on a webcam, USB camera, video file or RTSP/CCTV stream, with YOLO11 tracking, alarms, CSV logs and optional Arduino output.**

A free, open-source desktop object counter for Windows and Linux. Point it at a camera, drag the counting line onto the video, tick the classes you care about and press Start. Built on [Ultralytics YOLO](https://github.com/ultralytics/ultralytics) (YOLO11 nano by default, or your own trained `.pt`), OpenCV and PySide6.

![FAST Object Tracker window: live video with the counting line, per-class counts and the message log](docs/screenshot.png)

## Features

- **Any source**: built-in webcam, external USB cameras, video files (mp4, mkv, avi, mov...) and IP/CCTV cameras over RTSP or HTTP (Hikvision, Dahua, Reolink, DVR/NVR channels). Streams reconnect automatically when the link drops.
- **Two counting modes, each switchable**: count when the object's centre *crosses* the line (with IN/OUT direction) and/or when its box *touches* the line.
- **Draggable line**: move the end points or the whole line on the live video, at any time, without stopping.
- **Per-class counts**: tick any of the 80 COCO classes (person, car, truck, bus, bicycle, bottle, ...) or count everything. The table shows IN, OUT, TOUCH and total per class.
- **Base or custom models**: YOLO11 nano/small/medium and YOLOv8 nano/small download on first use from the official release. Or load your own `.pt` and optionally rename its classes.
- **Alarms**: beep, play a sound file or send a serial message when a class (or the total) reaches a count, once or every N objects. Optional snapshot on alarm.
- **Arduino / serial output**: write a message (`Go\r` by default) to a USB serial board on every count or alarm, so a relay, light, counter or printer can react. Auto-detects the board, reconnects when unplugged. See [docs/arduino.md](docs/arduino.md) for the sketch and wiring.
- **Logs and recordings**: a CSV with every count (time, frame, id, class, direction, totals), optional annotated MP4 recording, snapshots on demand.
- **Live message window** with colour-coded info/ok/warning/error lines, status lights for Source, Model and Serial, and fps / inference time.
- **Performance knobs**: image size, confidence and IoU thresholds, ByteTrack or BoT-SORT, run the model every Nth frame, CPU or CUDA.
- **Command line**: everything is scriptable with `--cli`.
- Dark, flat, professional interface. Settings are saved automatically.

## Download

Grab `FASTObjectTracker.exe` from the [Releases](https://github.com/PhantomAnas/FAST-Object-Tracker/releases) page (Windows, no install). The exe bundles PyTorch CPU and is large (several hundred MB). On first start the YOLO11 nano weights (about 6 MB) download next to the exe.

## Run from source

```bash
git clone https://github.com/PhantomAnas/FAST-Object-Tracker.git
cd FAST-Object-Tracker
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu   # or a CUDA build from pytorch.org
pip install -e .
python -m fasttracker
```

Python 3.10 or newer. For a GPU install the matching CUDA build of PyTorch first, then pick *CUDA GPU* in the Model card (or leave *Auto*).

## Quick start

1. **Source**: choose Webcam (press *Detect cameras* to find USB cams), a video file, or paste a stream URL such as `rtsp://user:password@192.168.1.64:554/Streaming/Channels/101`.
2. **Model**: keep YOLO11 nano. Tick the classes to count (default: person). For a custom model choose *Custom model (.pt)*, pick the file and press *Read classes*.
3. **Counting line**: drag the line on the video. Enable *cross*, *touch* or both. IN is the side labelled on the line; swap the end points to flip it.
4. **Alarms** (optional): *Add*, e.g. `person`, `50`, `Beep`.
5. **Arduino** (optional): enable, leave the port on *auto*, press *Test: send now*.
6. Press **Start** (F5). *Reset counts* (Ctrl+R) zeroes the table; *Snapshot* (Ctrl+S) saves the current frame; *Stop* (Esc).

Counts go to `counts_<date>.csv` in the log folder (shown in the messages), recordings and snapshots to `Videos\FAST Object Tracker` unless you choose another folder.

## Command line

```bash
python -m fasttracker --cli --source 0 --classes person --line 0.1,0.5,0.9,0.5
python -m fasttracker --cli --source traffic.mp4 --classes car,truck,bus --alarm car:100:beep --record
python -m fasttracker --cli --source rtsp://user:pass@192.168.1.10:554/live --touch on --cross off --serial
python -m fasttracker --cli --model my_bottles.pt --class-names "bottle,cap" --classes bottle --imgsz 416
python -m fasttracker --cli --list-webcams
python -m fasttracker --cli --list-ports
python -m fasttracker --cli --help
```

Add `--show` for a preview window, `--max-frames N` to stop after N frames, `--save-settings` to make the options the GUI defaults.

## Tips for accurate counting

- Place the line where objects move *across* it, not along it, and away from the frame edge so the tracker has a few frames before and after.
- Raise *Seen for at least* (frames) to ignore one-frame false detections; raise the confidence threshold if background objects get counted.
- On CPU use image size 320-480 and *Detect every* 2 frames for smooth video; nano at 640 runs around 10-15 fps on a modern laptop CPU.
- For products on a conveyor, train a small YOLO model on your product (Ultralytics docs) and load it as a custom model; use *touch* mode if items pass under the camera.
- Stream lag: the app keeps the capture buffer at one frame and reads RTSP over TCP.

## Project layout

```
src/fasttracker/
  settings.py      dataclass + JSON persistence, validation
  counter.py       line geometry, cross/touch counting per track id (pure Python, tested)
  detector.py      Ultralytics YOLO wrapper (base/custom models, class names, device)
  source.py        OpenCV capture: webcam / file / RTSP with reconnect
  alarms.py        alarm rules, beep and sound playback
  serial_link.py   pyserial writer with auto-detect and reconnect
  annotate.py      boxes, trails, line and counts overlay
  pipeline.py      the loop: read -> track -> count -> alarms/serial/log -> draw
  cli.py           command line
  app/             PySide6 window, theme, widgets, worker threads
tests/             pytest suite (no model or camera required)
docs/arduino.md    sketch, wiring and settings for a serial board
scripts/           icon, sample video and screenshot generators
```

Run the tests with `pip install -e ".[dev]"` then `pytest`.

## Privacy

Everything runs locally. No frames, counts or settings leave your machine. The only network access is the one-time download of the base YOLO weights from the Ultralytics GitHub release. Stream passwords are stored in the local settings file and masked in the log.

## License

[AGPL-3.0](LICENSE), because the app links to Ultralytics YOLO, which is AGPL-3.0 licensed. Commercial use of Ultralytics models may require an [Ultralytics Enterprise License](https://www.ultralytics.com/license).

## Keywords

object counter, people counter, vehicle counter, line crossing detection, YOLO11, YOLOv8, Ultralytics, ByteTrack, object tracking, RTSP, CCTV, IP camera, OpenCV, PySide6, Arduino, production line counting, traffic counting, Python desktop app.
