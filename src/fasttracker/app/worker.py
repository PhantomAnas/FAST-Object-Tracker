"""Background jobs: the tracking pipeline on its own QThread, plus small
thread-pool jobs for probing webcams, serial ports and model classes."""

from __future__ import annotations

import copy
import traceback

import numpy as np
from PySide6.QtCore import QObject, QRunnable, Signal
from PySide6.QtGui import QImage

from .. import pipeline as pl
from ..detector import Detector, DetectorError
from ..settings import TrackerSettings


def to_qimage(bgr: np.ndarray) -> QImage:
    rgb = np.ascontiguousarray(bgr[:, :, ::-1])
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()


class PipelineWorker(QObject):
    frame = Signal(QImage)
    stats = Signal(object)
    event = Signal(object, int)
    message = Signal(str, str)
    alarm = Signal(object, int)
    status = Signal(str, bool)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.pipeline: pl.Pipeline | None = None
        self.settings = TrackerSettings()
        self._alive = True

    def prepare(self, settings: TrackerSettings) -> None:
        self.settings = copy.deepcopy(settings)
        cb = pl.Callbacks()
        cb.on_frame = lambda f: self._emit(self.frame, to_qimage(f))
        cb.on_stats = lambda st: self._emit(self.stats, st)
        cb.on_event = lambda ev, total: self._emit(self.event, ev, total)
        cb.on_message = lambda lvl, txt: self._emit(self.message, lvl, txt)
        cb.on_alarm = lambda rule, count: self._emit(self.alarm, rule, count)
        cb.on_status = lambda name, ok: self._emit(self.status, name, ok)
        self.pipeline = pl.Pipeline(self.settings, cb)

    def _emit(self, signal, *args) -> None:
        if self._alive:
            try:
                signal.emit(*args)
            except RuntimeError:
                self._alive = False

    def run(self) -> None:
        if self.pipeline is None:
            return
        try:
            stats = self.pipeline.run()
        except pl.PipelineError as exc:
            self._emit(self.failed, str(exc))
            return
        except Exception:  # noqa: BLE001
            self._emit(self.failed, "unexpected error:\n" + traceback.format_exc())
            return
        self._emit(self.finished, stats)

    def stop(self) -> None:
        if self.pipeline is not None:
            self.pipeline.stop()


class ProbeSignals(QObject):
    webcams = Signal(list)
    ports = Signal(list)
    classes = Signal(str, list)        # model path, names
    failed = Signal(str, str)          # what, error


class WebcamProbe(QRunnable):
    def __init__(self, signals: ProbeSignals) -> None:
        super().__init__()
        self.signals = signals

    def run(self) -> None:
        try:
            from ..source import list_webcams
            self.signals.webcams.emit(list_webcams())
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit("webcams", str(exc))


class PortProbe(QRunnable):
    def __init__(self, signals: ProbeSignals) -> None:
        super().__init__()
        self.signals = signals

    def run(self) -> None:
        try:
            from ..serial_link import list_ports
            self.signals.ports.emit(list_ports())
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit("ports", str(exc))


class ClassProbe(QRunnable):
    """Loads a model once to read its class names (downloads base weights if needed)."""

    def __init__(self, model: str, class_names: str, signals: ProbeSignals) -> None:
        super().__init__()
        self.model, self.class_names, self.signals = model, class_names, signals

    def run(self) -> None:
        try:
            det = Detector(self.model, "cpu", self.class_names)
            info = det.load()
            self.signals.classes.emit(self.model, [info.names[k] for k in sorted(info.names)])
        except DetectorError as exc:
            self.signals.failed.emit("classes", str(exc))
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit("classes", f"{type(exc).__name__}: {exc}")
