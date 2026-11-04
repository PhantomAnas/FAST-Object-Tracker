"""The main window: settings cards on the left, live video + counts + log on the right."""

from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys

from PySide6.QtCore import QThread, QThreadPool, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import __version__
from ..detector import COCO_NAMES
from ..settings import ALARM_ACTIONS, KNOWN_MODELS, AlarmRule, TrackerSettings
from . import icons, theme, widgets as w
from .worker import ClassProbe, PipelineWorker, PortProbe, ProbeSignals, WebcamProbe

DOCS_URL = "https://github.com/PhantomAnas/FAST-Object-Tracker"
LEVEL_COLORS = {"info": theme.MUTED_HEX, "ok": theme.GREEN, "warn": theme.ORANGE, "error": theme.RED}


def _open_folder(path: str) -> None:
    try:
        os.makedirs(path, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except OSError:
        pass


class AlarmDialog(QDialog):
    def __init__(self, classes: list[str], rule: AlarmRule | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Alarm rule")
        self.setMinimumWidth(380)
        form = QFormLayout(self)
        form.setSpacing(10)
        self.cls = QComboBox()
        self.cls.setEditable(True)
        self.cls.addItem("any object (*)", "*")
        for c in classes:
            self.cls.addItem(c, c)
        self.count = QSpinBox()
        self.count.setRange(1, 1_000_000)
        self.count.setValue(10)
        self.action = QComboBox()
        for a in ALARM_ACTIONS:
            self.action.addItem({"beep": "Beep", "sound": "Play a sound file", "serial": "Send serial message",
                                 "beep+serial": "Beep + serial message"}[a], a)
        self.sound = w.FilePicker("Sound file (.wav)", "bell", filter_="Sound (*.wav);;All files (*)")
        self.repeat = QCheckBox("Repeat every N objects (not just once)")
        form.addRow("Object class", self.cls)
        form.addRow("When count reaches", self.count)
        form.addRow("Action", self.action)
        form.addRow(self.sound)
        form.addRow(self.repeat)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.action.currentIndexChanged.connect(lambda: self.sound.setVisible(self.action.currentData() == "sound"))
        self.sound.setVisible(False)
        if rule:
            idx = self.cls.findData(rule.cls)
            if idx >= 0:
                self.cls.setCurrentIndex(idx)
            else:
                self.cls.setEditText(rule.cls)
            self.count.setValue(rule.count)
            self.action.setCurrentIndex(max(0, self.action.findData(rule.action)))
            self.sound.set_path(rule.sound_path)
            self.repeat.setChecked(rule.repeat)
            self.sound.setVisible(rule.action == "sound")

    def rule(self) -> AlarmRule:
        data = self.cls.currentData() if self.cls.currentText() == self.cls.itemText(self.cls.currentIndex()) else None
        cls = data or self.cls.currentText().strip() or "*"
        return AlarmRule(cls=cls, count=self.count.value(), action=self.action.currentData(),
                         sound_path=self.sound.path(), repeat=self.repeat.isChecked())


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"FAST Object Tracker {__version__}")
        self.resize(1380, 860)
        self.s = TrackerSettings.load()
        self.pool = QThreadPool.globalInstance()
        self.probe = ProbeSignals()
        self.probe.webcams.connect(self._on_webcams)
        self.probe.ports.connect(self._on_ports)
        self.probe.classes.connect(self._on_classes)
        self.probe.failed.connect(self._on_probe_failed)
        self.thread: QThread | None = None
        self.worker: PipelineWorker | None = None
        self.running = False
        self._known_classes: list[str] = list(COCO_NAMES)
        self._loading = True
        self._build()
        self._apply_settings()
        self._loading = False
        self._refresh_ports()
        self.log("info", "ready.  Choose a source, place the line on the video and press Start.")

    # ---------------------------------------------------------------- build
    def _build(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._top_bar())
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(self._left_panel())
        split.addWidget(self._right_panel())
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([440, 940])
        outer.addWidget(split, 1)

    def _top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("target", 22, theme.ACCENT, dpr=self.devicePixelRatioF()))
        title = QLabel("FAST Object Tracker")
        title.setObjectName("Title")
        lay.addWidget(ic)
        lay.addWidget(title)
        lay.addSpacing(16)
        self.light_source = w.StatusLight("Source")
        self.light_model = w.StatusLight("Model")
        self.light_serial = w.StatusLight("Serial")
        for light in (self.light_source, self.light_model, self.light_serial):
            lay.addWidget(light)
            lay.addSpacing(8)
        self.perf = QLabel("")
        self.perf.setObjectName("Mono")
        lay.addWidget(self.perf)
        lay.addStretch(1)
        self.btn_reset = w.pill("Reset counts", "rotate", tooltip="Set every count back to zero (Ctrl+R)")
        self.btn_snapshot = w.pill("Snapshot", "camera-snap", tooltip="Save the current annotated frame (Ctrl+S)")
        self.btn_folder = w.round_button("folder", "Open the output folder")
        self.btn_docs = w.round_button("book", "Open the documentation on GitHub")
        self.btn_start = w.pill("Start", "play", "Go", "Start tracking (F5)")
        self.btn_stop = w.pill("Stop", "stop", "Danger", "Stop tracking (Esc)")
        self.btn_stop.setEnabled(False)
        for b in (self.btn_reset, self.btn_snapshot, self.btn_folder, self.btn_docs, self.btn_start, self.btn_stop):
            lay.addWidget(b)
        self.btn_start.clicked.connect(self.start)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_reset.clicked.connect(self.reset_counts)
        self.btn_snapshot.clicked.connect(self.snapshot)
        self.btn_folder.clicked.connect(lambda: _open_folder(self.s.default_output_folder()))
        self.btn_docs.clicked.connect(self._open_docs)
        for seq, fn in ((QKeySequence("F5"), self.start), (QKeySequence("Esc"), self.stop),
                        (QKeySequence("Ctrl+R"), self.reset_counts), (QKeySequence("Ctrl+S"), self.snapshot)):
            act = QAction(self)
            act.setShortcut(seq)
            act.triggered.connect(fn)
            self.addAction(act)
        return bar

    def _left_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(380)
        scroll.setMaximumWidth(560)
        inner = QWidget()
        inner.setMinimumWidth(0)
        col = QVBoxLayout(inner)
        col.setContentsMargins(14, 14, 8, 14)
        col.setSpacing(12)
        col.addWidget(self._source_card())
        col.addWidget(self._model_card())
        col.addWidget(self._counting_card())
        col.addWidget(self._alarm_card())
        col.addWidget(self._serial_card())
        col.addWidget(self._output_card())
        col.addStretch(1)
        scroll.setWidget(inner)
        return scroll

    def _source_card(self) -> QWidget:
        card = w.Card("Source", "camera")
        self.src_kind = w.Segmented([("webcam", "Webcam / USB"), ("file", "Video file"), ("url", "IP / CCTV")])
        card.body.addWidget(self.src_kind)
        # webcam
        self.page_webcam = QWidget()
        lay = QVBoxLayout(self.page_webcam)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.cam_index = QComboBox()
        self.cam_index.setEditable(True)
        for i in range(4):
            self.cam_index.addItem(f"Camera {i}", i)
        self.btn_probe_cams = w.pill("Detect cameras", "refresh")
        lay.addLayout(w.row("Camera", self.cam_index, self.btn_probe_cams))
        lay.addWidget(w.hint("0 is usually the built-in webcam; external USB cameras are 1, 2...  'Detect' tests each index."))
        card.body.addWidget(self.page_webcam)
        # file
        self.page_file = QWidget()
        lay = QVBoxLayout(self.page_file)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.file_pick = w.FilePicker("Video file", "film", filter_="Video (*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.mpg *.wmv *.ts);;All files (*)")
        self.loop_file = QCheckBox("Loop the video")
        lay.addWidget(self.file_pick)
        lay.addWidget(self.loop_file)
        card.body.addWidget(self.page_file)
        # url
        self.page_url = QWidget()
        lay = QVBoxLayout(self.page_url)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.url = QLineEdit()
        self.url.setPlaceholderText("rtsp://user:password@192.168.1.64:554/Streaming/Channels/101")
        self.reconnect = QCheckBox("Reconnect automatically when the stream drops")
        lay.addWidget(self.url)
        lay.addWidget(self.reconnect)
        lay.addWidget(w.hint("Works with RTSP/HTTP streams from CCTV DVRs/NVRs and IP cameras (Hikvision, Dahua, Reolink...). "
                             "The password is stored in the settings file on this PC and hidden in the log."))
        card.body.addWidget(self.page_url)
        self.src_kind.changed.connect(self._on_source_kind)
        self.btn_probe_cams.clicked.connect(self._probe_cams)
        for sig in (self.cam_index.currentIndexChanged, self.cam_index.editTextChanged, self.file_pick.changed,
                    self.loop_file.toggled, self.url.textChanged, self.reconnect.toggled):
            sig.connect(self._dirty)
        return card

    def _model_card(self) -> QWidget:
        card = w.Card("Model", "cpu")
        self.model_combo = QComboBox()
        for name, label in KNOWN_MODELS.items():
            self.model_combo.addItem(label, name)
        self.model_combo.addItem("Custom model (.pt)...", "custom")
        card.body.addWidget(self.model_combo)
        self.custom_pick = w.FilePicker("Your trained model", "cpu", filter_="PyTorch model (*.pt);;All files (*)")
        self.class_names = QLineEdit()
        self.class_names.setPlaceholderText("optional: rename classes, e.g. bottle, cap, label")
        self.custom_box = QWidget()
        lay = QVBoxLayout(self.custom_box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(self.custom_pick)
        lay.addWidget(self.class_names)
        card.body.addWidget(self.custom_box)
        card.body.addWidget(w.hint("Base models download once (~6 MB for nano) from the official Ultralytics release. "
                                   "Use nano on CPU; small/medium need a GPU for real time."))
        # classes
        head = QHBoxLayout()
        head.addWidget(w.hint("Count these classes (none ticked = every class)"), 1)
        self.btn_load_classes = w.pill("Read classes", "refresh", tooltip="Load the model to list its classes")
        self.btn_class_none = w.pill("Clear")
        head.addWidget(self.btn_load_classes)
        head.addWidget(self.btn_class_none)
        card.body.addLayout(head)
        self.class_filter = QLineEdit()
        self.class_filter.setPlaceholderText("filter classes...")
        card.body.addWidget(self.class_filter)
        self.class_list = QListWidget()
        self.class_list.setFixedHeight(150)
        card.body.addWidget(self.class_list)
        # params
        self.conf = w.LabeledSlider("Confidence threshold", 0.05, 0.95, 0.05)
        self.iou = w.LabeledSlider("Overlap (IoU) threshold", 0.1, 0.9, 0.05)
        card.body.addWidget(self.conf)
        card.body.addWidget(self.iou)
        self.imgsz = QComboBox()
        for v in (320, 416, 480, 640, 800, 960, 1280):
            self.imgsz.addItem(str(v), v)
        self.device = QComboBox()
        self.device.addItem("Auto (GPU if available)", "auto")
        self.device.addItem("CPU", "cpu")
        self.device.addItem("CUDA GPU", "cuda")
        self.tracker = QComboBox()
        self.tracker.addItem("ByteTrack (fast)", "bytetrack")
        self.tracker.addItem("BoT-SORT (steadier ids)", "botsort")
        self.detect_every = QSpinBox()
        self.detect_every.setRange(1, 10)
        self.detect_every.setSuffix(" frame(s)")
        grid = QFormLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)
        for lbl, wdg in (("Image size", self.imgsz), ("Device", self.device), ("Tracker", self.tracker), ("Detect every", self.detect_every)):
            cap = QLabel(lbl)
            cap.setObjectName("Hint")
            grid.addRow(cap, wdg)
        card.body.addLayout(grid)
        card.body.addWidget(w.hint("Lower the image size or detect every 2-3 frames if the video is choppy on CPU."))
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        self.custom_pick.changed.connect(self._on_model_changed)
        self.class_names.editingFinished.connect(self._on_model_changed)
        self.btn_load_classes.clicked.connect(self._load_classes)
        self.btn_class_none.clicked.connect(self._clear_classes)
        self.class_filter.textChanged.connect(self._filter_classes)
        self.class_list.itemChanged.connect(self._dirty)
        for sig in (self.conf.valueChanged, self.iou.valueChanged, self.imgsz.currentIndexChanged,
                    self.device.currentIndexChanged, self.tracker.currentIndexChanged, self.detect_every.valueChanged):
            sig.connect(self._dirty)
        return card

    def _counting_card(self) -> QWidget:
        card = w.Card("Counting line", "target")
        self.count_cross = QCheckBox("Count when the object's centre crosses the line")
        self.count_touch = QCheckBox("Count when the object's box touches the line")
        card.body.addWidget(self.count_cross)
        card.body.addWidget(self.count_touch)
        self.direction = w.Segmented([("both", "Both ways"), ("in", "IN only"), ("out", "OUT only")])
        card.body.addLayout(w.row("Crossing direction", self.direction, stretch_last=True))
        self.min_frames = QSpinBox()
        self.min_frames.setRange(1, 30)
        self.min_frames.setSuffix(" frames")
        self.btn_line_h = w.pill("Horizontal")
        self.btn_line_v = w.pill("Vertical")
        card.body.addLayout(w.row("Seen for at least", self.min_frames))
        card.body.addLayout(w.row("Reset line", self.btn_line_h, self.btn_line_v))
        card.body.addWidget(w.hint("Drag the end points (or the whole line) on the video. IN is the side marked on the line; "
                                   "swap the end points to flip it. 'Seen for' filters one-frame false detections."))
        self.btn_line_h.clicked.connect(lambda: self._set_line((0.1, 0.5, 0.9, 0.5)))
        self.btn_line_v.clicked.connect(lambda: self._set_line((0.5, 0.1, 0.5, 0.9)))
        for sig in (self.count_cross.toggled, self.count_touch.toggled, self.direction.changed, self.min_frames.valueChanged):
            sig.connect(self._dirty)
        return card

    def _alarm_card(self) -> QWidget:
        card = w.Card("Alarms", "bell")
        self.alarm_list = QListWidget()
        self.alarm_list.setFixedHeight(96)
        card.body.addWidget(self.alarm_list)
        self.btn_alarm_add = w.pill("Add", "plus")
        self.btn_alarm_edit = w.pill("Edit")
        self.btn_alarm_del = w.pill("Remove", "minus")
        card.body.addLayout(w.row(self.btn_alarm_add, self.btn_alarm_edit, self.btn_alarm_del))
        self.beep_on_count = QCheckBox("Short beep on every count")
        card.body.addWidget(self.beep_on_count)
        card.body.addWidget(w.hint("Example: beep when 50 cars have passed, or send a serial message every 10 bottles."))
        self.btn_alarm_add.clicked.connect(self._alarm_add)
        self.btn_alarm_edit.clicked.connect(self._alarm_edit)
        self.btn_alarm_del.clicked.connect(self._alarm_del)
        self.alarm_list.itemDoubleClicked.connect(lambda _i: self._alarm_edit())
        self.alarm_list.itemChanged.connect(self._alarm_toggled)
        self.beep_on_count.toggled.connect(self._dirty)
        return card

    def _serial_card(self) -> QWidget:
        card = w.Card("Arduino / serial output", "usb")
        self.serial_enabled = QCheckBox("Send a serial message to a connected board")
        card.body.addWidget(self.serial_enabled)
        self.serial_box = QWidget()
        lay = QVBoxLayout(self.serial_box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.port = QComboBox()
        self.port.setEditable(True)
        self.btn_ports = w.round_button("refresh", "Refresh the port list")
        self.baud = QComboBox()
        self.baud.setEditable(True)
        for b in (9600, 19200, 38400, 57600, 115200):
            self.baud.addItem(str(b), b)
        lay.addLayout(w.row("Port", self.port, self.btn_ports, stretch_last=False))
        lay.addLayout(w.row("Baud", self.baud))
        self.serial_message = QLineEdit()
        self.serial_on = w.Segmented([("count", "Every count"), ("alarm", "Alarms only"), ("never", "Never")])
        lay.addLayout(w.row("Message", self.serial_message, stretch_last=True))
        lay.addLayout(w.row("Send on", self.serial_on, stretch_last=True))
        self.btn_serial_test = w.pill("Test: send now", "usb")
        lay.addLayout(w.row(self.btn_serial_test))
        lay.addWidget(w.hint("Leave the port on 'auto' to pick the first USB serial board. Escapes like \\r and \\n are allowed. "
                             "See docs/arduino.md for the sketch and wiring."))
        card.body.addWidget(self.serial_box)
        self.serial_enabled.toggled.connect(self._dirty)
        self.serial_enabled.toggled.connect(self.serial_box.setEnabled)
        self.btn_ports.clicked.connect(self._refresh_ports)
        self.btn_serial_test.clicked.connect(self._serial_test)
        for sig in (self.port.currentIndexChanged, self.port.editTextChanged, self.baud.currentIndexChanged,
                    self.baud.editTextChanged, self.serial_message.textChanged, self.serial_on.changed):
            sig.connect(self._dirty)
        return card

    def _output_card(self) -> QWidget:
        card = w.Card("Display and output", "save")
        self.show_trails = QCheckBox("Draw motion trails")
        self.show_labels = QCheckBox("Draw class labels and ids")
        self.show_conf = QCheckBox("Show confidence in labels")
        self.log_csv = QCheckBox("Write every count to a CSV log")
        self.record_video = QCheckBox("Record the annotated video (MP4)")
        self.snapshot_on_alarm = QCheckBox("Save a snapshot when an alarm fires")
        for cb in (self.show_trails, self.show_labels, self.show_conf, self.log_csv, self.record_video, self.snapshot_on_alarm):
            card.body.addWidget(cb)
            cb.toggled.connect(self._dirty)
        self.output_pick = w.FilePicker("Output folder (recordings, snapshots)", "folder", mode="dir", placeholder="Videos\\FAST Object Tracker")
        self.log_pick = w.FilePicker("CSV log folder", "folder", mode="dir", placeholder="app data folder")
        card.body.addWidget(self.output_pick)
        card.body.addWidget(self.log_pick)
        self.output_pick.changed.connect(self._dirty)
        self.log_pick.changed.connect(self._dirty)
        return card

    def _right_panel(self) -> QWidget:
        panel = QWidget()
        col = QVBoxLayout(panel)
        col.setContentsMargins(8, 14, 14, 14)
        col.setSpacing(12)
        self.video = w.VideoView()
        self.video.lineChanged.connect(self._on_line_dragged)
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.setChildrenCollapsible(False)
        vsplit.addWidget(self.video)
        bottom = QWidget()
        blay = QHBoxLayout(bottom)
        blay.setContentsMargins(0, 0, 0, 0)
        blay.setSpacing(12)
        # counts
        counts = w.Card("Counts", "activity")
        self.total_lbl = QLabel("0")
        self.total_lbl.setObjectName("Big")
        counts.head.insertWidget(counts.head.count() - 1, self.total_lbl)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["CLASS", "IN", "OUT", "TOUCH", "TOTAL"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 5):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumWidth(320)
        counts.body.addWidget(self.table)
        blay.addWidget(counts, 2)
        # log
        logcard = w.Card("Messages", "list")
        self.btn_clear_log = w.round_button("x", "Clear messages")
        logcard.head.insertWidget(logcard.head.count(), self.btn_clear_log)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(600)
        logcard.body.addWidget(self.log_view)
        self.btn_clear_log.clicked.connect(self.log_view.clear)
        blay.addWidget(logcard, 3)
        bottom.setMinimumHeight(170)
        vsplit.addWidget(bottom)
        vsplit.setStretchFactor(0, 1)
        vsplit.setStretchFactor(1, 0)
        vsplit.setSizes([560, 220])
        col.addWidget(vsplit, 1)
        return panel

    # ------------------------------------------------------------- settings
    def _apply_settings(self) -> None:
        s = self.s
        self.src_kind.set_value(s.source_kind)
        self._on_source_kind(s.source_kind)
        idx = self.cam_index.findData(s.webcam_index)
        if idx >= 0:
            self.cam_index.setCurrentIndex(idx)
        else:
            self.cam_index.setEditText(str(s.webcam_index))
        self.file_pick.set_path(s.file_path)
        self.loop_file.setChecked(s.loop_file)
        self.url.setText(s.url)
        self.reconnect.setChecked(s.reconnect)
        if s.model in KNOWN_MODELS:
            self.model_combo.setCurrentIndex(self.model_combo.findData(s.model))
        else:
            self.model_combo.setCurrentIndex(self.model_combo.findData("custom"))
            self.custom_pick.set_path(s.model)
        self.class_names.setText(s.class_names)
        self.custom_box.setVisible(self.model_combo.currentData() == "custom")
        self._fill_classes(self._known_classes, s.classes)
        self.conf.set_value(s.conf)
        self.iou.set_value(s.iou)
        self.imgsz.setCurrentIndex(max(0, self.imgsz.findData(s.imgsz)))
        self.device.setCurrentIndex(max(0, self.device.findData(s.device)))
        self.tracker.setCurrentIndex(max(0, self.tracker.findData(s.tracker)))
        self.detect_every.setValue(s.detect_every)
        self.count_cross.setChecked(s.count_cross)
        self.count_touch.setChecked(s.count_touch)
        self.direction.set_value(s.direction)
        self.min_frames.setValue(s.min_track_frames)
        self.video.set_line(s.line)
        self._fill_alarms()
        self.beep_on_count.setChecked(s.beep_on_count)
        self.serial_enabled.setChecked(s.serial_enabled)
        self.serial_box.setEnabled(s.serial_enabled)
        self.port.setEditText(s.serial_port or "auto")
        self.baud.setEditText(str(s.serial_baud))
        self.serial_message.setText(s.serial_message)
        self.serial_on.set_value(s.serial_on)
        self.show_trails.setChecked(s.show_trails)
        self.show_labels.setChecked(s.show_labels)
        self.show_conf.setChecked(s.show_conf)
        self.log_csv.setChecked(s.log_csv)
        self.record_video.setChecked(s.record_video)
        self.snapshot_on_alarm.setChecked(s.snapshot_on_alarm)
        self.output_pick.set_path(s.output_folder)
        self.log_pick.set_path(s.log_folder)

    def _collect(self) -> TrackerSettings:
        s = self.s
        s.source_kind = self.src_kind.value()
        try:
            data = self.cam_index.currentData()
            s.webcam_index = int(data) if data is not None and self.cam_index.currentText() == self.cam_index.itemText(self.cam_index.currentIndex()) \
                else int("".join(ch for ch in self.cam_index.currentText() if ch.isdigit()) or 0)
        except (TypeError, ValueError):
            s.webcam_index = 0
        s.file_path = self.file_pick.path()
        s.loop_file = self.loop_file.isChecked()
        s.url = self.url.text().strip()
        s.reconnect = self.reconnect.isChecked()
        s.model = self.custom_pick.path() if self.model_combo.currentData() == "custom" else self.model_combo.currentData()
        s.class_names = self.class_names.text().strip()
        s.classes = [self.class_list.item(i).text() for i in range(self.class_list.count())
                     if self.class_list.item(i).checkState() == Qt.CheckState.Checked]
        s.conf = round(self.conf.value(), 2)
        s.iou = round(self.iou.value(), 2)
        s.imgsz = int(self.imgsz.currentData())
        s.device = self.device.currentData()
        s.tracker = self.tracker.currentData()
        s.detect_every = self.detect_every.value()
        s.count_cross = self.count_cross.isChecked()
        s.count_touch = self.count_touch.isChecked()
        s.direction = self.direction.value()
        s.min_track_frames = self.min_frames.value()
        s.line = tuple(round(v, 4) for v in self.video.line)  # type: ignore[assignment]
        s.beep_on_count = self.beep_on_count.isChecked()
        s.serial_enabled = self.serial_enabled.isChecked()
        port = self.port.currentText().strip()
        s.serial_port = "" if port.lower() in ("", "auto") else port.split(" ")[0]
        try:
            s.serial_baud = int(self.baud.currentText().strip())
        except ValueError:
            s.serial_baud = 9600
        s.serial_message = self.serial_message.text()
        s.serial_on = self.serial_on.value()
        s.show_trails = self.show_trails.isChecked()
        s.show_labels = self.show_labels.isChecked()
        s.show_conf = self.show_conf.isChecked()
        s.log_csv = self.log_csv.isChecked()
        s.record_video = self.record_video.isChecked()
        s.snapshot_on_alarm = self.snapshot_on_alarm.isChecked()
        s.output_folder = self.output_pick.path()
        s.log_folder = self.log_pick.path()
        return s

    def _dirty(self, *_a) -> None:
        if self._loading:
            return
        self._collect()
        if not hasattr(self, "_save_timer"):
            self._save_timer = QTimer(self)
            self._save_timer.setSingleShot(True)
            self._save_timer.timeout.connect(self._save)
        self._save_timer.start(800)

    def _save(self) -> None:
        try:
            self.s.save()
        except OSError as exc:
            self.log("warn", f"could not save settings: {exc}")

    # ------------------------------------------------------------ handlers
    def _on_source_kind(self, kind: str) -> None:
        self.page_webcam.setVisible(kind == "webcam")
        self.page_file.setVisible(kind == "file")
        self.page_url.setVisible(kind == "url")
        self._dirty()

    def _probe_cams(self) -> None:
        self.btn_probe_cams.setEnabled(False)
        self.log("info", "probing cameras 0-5 (this takes a few seconds)...")
        self.pool.start(WebcamProbe(self.probe))

    def _on_webcams(self, found: list) -> None:
        self.btn_probe_cams.setEnabled(True)
        current = self.cam_index.currentText()
        self.cam_index.clear()
        for i in (found or range(4)):
            self.cam_index.addItem(f"Camera {i}" + ("" if found else " (untested)"), i)
        idx = self.cam_index.findText(current)
        self.cam_index.setCurrentIndex(idx if idx >= 0 else 0)
        self.log("ok" if found else "warn", f"cameras found: {', '.join(map(str, found))}" if found else "no camera answered on indices 0-5")

    def _on_model_changed(self, *_a) -> None:
        custom = self.model_combo.currentData() == "custom"
        self.custom_box.setVisible(custom)
        if not custom and self._known_classes != COCO_NAMES:
            self._known_classes = list(COCO_NAMES)
            self._fill_classes(self._known_classes, self._checked_classes())
        self._dirty()

    def _checked_classes(self) -> list[str]:
        return [self.class_list.item(i).text() for i in range(self.class_list.count())
                if self.class_list.item(i).checkState() == Qt.CheckState.Checked]

    def _fill_classes(self, names: list[str], checked: list[str]) -> None:
        self.class_list.blockSignals(True)
        self.class_list.clear()
        lower = {c.lower() for c in checked}
        for n in names:
            item = QListWidgetItem(n)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if n.lower() in lower else Qt.CheckState.Unchecked)
            self.class_list.addItem(item)
        # keep chosen names that the model does not know (e.g. custom model not loaded yet)
        for c in checked:
            if c.lower() not in {n.lower() for n in names}:
                item = QListWidgetItem(c)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                self.class_list.addItem(item)
        self.class_list.blockSignals(False)
        self._filter_classes(self.class_filter.text())

    def _filter_classes(self, text: str) -> None:
        t = text.strip().lower()
        for i in range(self.class_list.count()):
            item = self.class_list.item(i)
            item.setHidden(bool(t) and t not in item.text().lower() and item.checkState() != Qt.CheckState.Checked)

    def _clear_classes(self) -> None:
        self.class_list.blockSignals(True)
        for i in range(self.class_list.count()):
            self.class_list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self.class_list.blockSignals(False)
        self._dirty()

    def _load_classes(self) -> None:
        s = self._collect()
        if not s.model:
            self.log("warn", "choose a model file first")
            return
        self.btn_load_classes.setEnabled(False)
        self.log("info", f"reading classes from {os.path.basename(s.model)}...")
        self.pool.start(ClassProbe(s.model, s.class_names, self.probe))

    def _on_classes(self, model: str, names: list) -> None:
        self.btn_load_classes.setEnabled(True)
        self._known_classes = list(names)
        self._fill_classes(names, self._checked_classes())
        self.log("ok", f"{len(names)} classes: " + ", ".join(names[:12]) + (" ..." if len(names) > 12 else ""))
        self._dirty()

    def _on_probe_failed(self, what: str, error: str) -> None:
        self.btn_load_classes.setEnabled(True)
        self.btn_probe_cams.setEnabled(True)
        self.log("error", f"{what}: {error}")

    def _set_line(self, line) -> None:
        self.video.set_line(line)
        self._on_line_dragged(tuple(line))

    def _on_line_dragged(self, line: tuple) -> None:
        self.s.line = tuple(round(float(v), 4) for v in line)  # type: ignore[assignment]
        if self.worker is not None and self.running:
            self.worker.pipeline.set_line(self.s.line)
        self._dirty()

    def _fill_alarms(self) -> None:
        self.alarm_list.blockSignals(True)
        self.alarm_list.clear()
        for rule in self.s.alarms:
            item = QListWidgetItem(rule.describe())
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if rule.enabled else Qt.CheckState.Unchecked)
            self.alarm_list.addItem(item)
        self.alarm_list.blockSignals(False)

    def _alarm_add(self) -> None:
        dlg = AlarmDialog(self._known_classes, None, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.s.alarms.append(dlg.rule())
            self._fill_alarms()
            self._dirty()

    def _alarm_edit(self) -> None:
        i = self.alarm_list.currentRow()
        if i < 0 or i >= len(self.s.alarms):
            return
        dlg = AlarmDialog(self._known_classes, self.s.alarms[i], self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            rule = dlg.rule()
            rule.enabled = self.s.alarms[i].enabled
            self.s.alarms[i] = rule
            self._fill_alarms()
            self._dirty()

    def _alarm_del(self) -> None:
        i = self.alarm_list.currentRow()
        if 0 <= i < len(self.s.alarms):
            del self.s.alarms[i]
            self._fill_alarms()
            self._dirty()

    def _alarm_toggled(self, item: QListWidgetItem) -> None:
        i = self.alarm_list.row(item)
        if 0 <= i < len(self.s.alarms):
            self.s.alarms[i].enabled = item.checkState() == Qt.CheckState.Checked
            self._dirty()

    def _refresh_ports(self) -> None:
        self.pool.start(PortProbe(self.probe))

    def _on_ports(self, ports: list) -> None:
        current = self.port.currentText()
        self.port.blockSignals(True)
        self.port.clear()
        self.port.addItem("auto")
        for dev, desc in ports:
            self.port.addItem(f"{dev}  {desc}".strip() if desc else dev)
        idx = self.port.findText(current, Qt.MatchFlag.MatchStartsWith) if current else 0
        self.port.setCurrentIndex(max(0, idx))
        if current and idx < 0:
            self.port.setEditText(current)
        self.port.blockSignals(False)
        if ports:
            self.log("info", "serial ports: " + ", ".join(d for d, _ in ports))

    def _serial_test(self) -> None:
        s = self._collect()
        if self.worker is not None and self.running and self.worker.pipeline.serial is not None:
            ok = self.worker.pipeline.serial.pulse()
            self.log("ok" if ok else "warn", "serial test message sent" if ok else "serial write failed")
            return
        from ..serial_link import SerialError, SerialLink
        link = SerialLink(s.serial_port, s.serial_baud, s.serial_bytes)
        try:
            port = link.open()
            ok = link.pulse()
            self.log("ok" if ok else "warn", f"sent {s.serial_bytes!r} to {port}" if ok else f"could not write to {port}")
        except SerialError as exc:
            self.log("error", f"serial: {exc}")
        finally:
            link.close()

    def _open_docs(self) -> None:
        import webbrowser
        webbrowser.open(DOCS_URL)

    # ----------------------------------------------------------------- run
    def start(self) -> None:
        if self.running:
            return
        s = self._collect()
        problems = s.validate()
        if problems:
            self.log("error", "cannot start: " + "; ".join(problems))
            QMessageBox.warning(self, "Check the settings", "\n".join(f"- {p}" for p in problems))
            return
        self._save()
        self.worker = PipelineWorker()
        self.worker.prepare(s)
        self.thread = QThread(self)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.frame.connect(self.video.set_frame)
        self.worker.stats.connect(self._on_stats)
        self.worker.event.connect(self._on_event)
        self.worker.message.connect(self.log)
        self.worker.alarm.connect(self._on_alarm)
        self.worker.status.connect(self._on_status)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.running = True
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._set_inputs_enabled(False)
        self.thread.start()

    def stop(self) -> None:
        if self.worker is not None and self.running:
            self.worker.stop()
            self.log("info", "stopping...")

    def _teardown(self) -> None:
        self.running = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._set_inputs_enabled(True)
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(5000)
        self.thread = None
        self.worker = None
        self.light_model.set_state(None)
        self.light_source.set_state(None)
        self.light_serial.set_state(None)
        self.perf.setText("")

    def _set_inputs_enabled(self, on: bool) -> None:
        for wdg in (self.src_kind, self.page_webcam, self.page_file, self.page_url, self.model_combo, self.custom_box,
                    self.class_list, self.btn_load_classes, self.btn_class_none, self.imgsz, self.device, self.tracker,
                    self.serial_enabled, self.count_cross, self.count_touch, self.direction, self.record_video,
                    self.log_csv, self.output_pick, self.log_pick, self.btn_line_h, self.btn_line_v):
            wdg.setEnabled(on)
        self.serial_box.setEnabled(on and self.serial_enabled.isChecked())

    def _on_finished(self, stats) -> None:
        self._teardown()
        self._on_stats(stats)

    def _on_failed(self, error: str) -> None:
        self.log("error", error)
        self._teardown()

    def _on_status(self, name: str, ok: bool) -> None:
        light = {"source": self.light_source, "model": self.light_model, "serial": self.light_serial}.get(name)
        if light:
            light.set_state(ok if (name != "serial" or self.s.serial_enabled) else None)

    def _on_stats(self, st) -> None:
        self.total_lbl.setText(str(st.total))
        rows = sorted(st.totals.items())
        self.table.setRowCount(len(rows))
        for r, (name, v) in enumerate(rows):
            vals = [name, v["in"], v["out"], v["touch"], v["in"] + v["out"] + v["touch"]]
            for c, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                if c:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, c, item)
        if self.running:
            self.perf.setText(f"{st.fps:.1f} fps   {st.infer_ms:.0f} ms/frame   {st.tracked} tracked   {st.width}x{st.height}")

    def _on_event(self, ev, total: int) -> None:
        d = f" {ev.direction.upper()}" if ev.direction else ""
        self.log("ok", f"#{ev.track_id} {ev.name} {ev.kind}{d}  ->  total {total}")

    def _on_alarm(self, rule, count: int) -> None:
        pass   # already logged by the pipeline; hook for future UI flashes

    def reset_counts(self) -> None:
        if self.worker is not None and self.running:
            self.worker.pipeline.reset_counts()
        self.total_lbl.setText("0")
        self.table.setRowCount(0)

    def snapshot(self) -> None:
        if self.worker is not None and self.running:
            self.worker.pipeline.snapshot()
        else:
            self.log("warn", "start tracking first to take a snapshot")

    # ----------------------------------------------------------------- log
    def log(self, level: str, text: str) -> None:
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(LEVEL_COLORS.get(level, theme.MUTED_HEX)))
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        dim = QTextCharFormat()
        dim.setForeground(QColor(theme.FAINT_HEX))
        cursor.insertText(f"{stamp}  ", dim)
        cursor.insertText(text + "\n", fmt)
        self.log_view.setTextCursor(cursor)
        self.log_view.ensureCursorVisible()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.running and self.worker is not None:
            self.worker.stop()
            if self.thread is not None:
                self.thread.quit()
                self.thread.wait(8000)
        self._collect()
        self._save()
        self.pool.waitForDone(3000)
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1] + (argv or []))
    app.setApplicationName("FAST Object Tracker")
    app.setStyleSheet(theme.STYLESHEET)
    icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "assets", "icon.png")
    if getattr(sys, "frozen", False):
        icon_path = os.path.join(getattr(sys, "_MEIPASS", ""), "assets", "icon.png")
    if os.path.isfile(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    win = MainWindow()
    win.show()
    return app.exec()
