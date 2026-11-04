"""YOLO detection + tracking through Ultralytics.  Models are never shipped:
the base weights download from the official release on first use, or you
point at your own .pt file."""

from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np

from .counter import Track
from .settings import KNOWN_MODELS


class DetectorError(Exception):
    pass


@dataclass
class ModelInfo:
    path: str
    names: dict[int, str]
    custom: bool
    device: str


COCO_NAMES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
]


def parse_class_names(text: str) -> list[str]:
    return [n.strip() for n in (text or "").replace(";", ",").split(",") if n.strip()]


def model_label(path: str) -> str:
    base = os.path.basename(path)
    return KNOWN_MODELS.get(base, base)


class Detector:
    """Loads lazily so the GUI opens instantly and import errors are readable."""

    def __init__(self, model: str, device: str = "auto", class_names: str = "", tracker: str = "bytetrack") -> None:
        self.model_path = model
        self.device = device
        self.names_override = parse_class_names(class_names)
        self.tracker = tracker if tracker.endswith(".yaml") else f"{tracker}.yaml"
        self._model = None
        self.info: ModelInfo | None = None

    # ------------------------------------------------------------- loading
    def load(self, log=None) -> ModelInfo:
        if self.info is not None:
            return self.info
        try:
            from ultralytics import YOLO
        except Exception as exc:  # noqa: BLE001
            raise DetectorError(f"Ultralytics could not be imported ({type(exc).__name__}: {exc}). "
                                "Run: pip install ultralytics") from exc
        path = self.model_path
        custom = path not in KNOWN_MODELS
        if custom and not os.path.isfile(path):
            raise DetectorError(f"model file not found: {path}")
        if not custom and log:
            log(f"loading {model_label(path)} (downloads ~6-50 MB from the Ultralytics release on first use)")
        try:
            self._model = YOLO(path)
        except Exception as exc:  # noqa: BLE001
            raise DetectorError(f"could not load the model '{path}': {exc}") from exc
        names = dict(getattr(self._model, "names", {}) or {})
        if self.names_override:
            names = {i: (self.names_override[i] if i < len(self.names_override) else n) for i, n in names.items()}
        device = self._resolve_device()
        self.info = ModelInfo(path, names, custom, device)
        if log:
            log(f"model ready: {len(names)} classes, device {device}")
        return self.info

    def _resolve_device(self) -> str:
        if self.device == "cpu":
            return "cpu"
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda:0"
        except Exception:  # noqa: BLE001
            pass
        if self.device == "cuda":
            raise DetectorError("CUDA was requested but no CUDA-capable GPU/PyTorch build was found; choose 'auto' or 'cpu'")
        return "cpu"

    @property
    def names(self) -> dict[int, str]:
        return self.info.names if self.info else {}

    def class_ids(self, wanted: list[str]) -> list[int] | None:
        """Ids for the wanted class names (None = everything).  Unknown names are ignored."""
        if not wanted:
            return None
        lookup = {n.lower(): i for i, n in self.names.items()}
        ids = [lookup[w.lower()] for w in wanted if w.lower() in lookup]
        return ids or None

    def unknown_classes(self, wanted: list[str]) -> list[str]:
        lookup = {n.lower() for n in self.names.values()}
        return [w for w in wanted if w.lower() not in lookup]

    # ------------------------------------------------------------ tracking
    def track(self, frame: np.ndarray, conf: float = 0.4, iou: float = 0.5, imgsz: int = 640,
              classes: list[int] | None = None, max_det: int = 100) -> list[Track]:
        if self._model is None:
            self.load()
        assert self.info is not None
        try:
            results = self._model.track(frame, persist=True, verbose=False, conf=conf, iou=iou, imgsz=imgsz,
                                        classes=classes, max_det=max_det, tracker=self.tracker,
                                        device=self.info.device)
        except Exception as exc:  # noqa: BLE001
            raise DetectorError(f"inference failed: {exc}") from exc
        out: list[Track] = []
        if not results:
            return out
        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0 or boxes.id is None:
            return out
        xyxy = boxes.xyxy.cpu().numpy()
        ids = boxes.id.int().cpu().numpy()
        cls = boxes.cls.int().cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        names = self.info.names
        for i in range(len(ids)):
            x1, y1, x2, y2 = (float(v) for v in xyxy[i])
            out.append(Track(int(ids[i]), names.get(int(cls[i]), str(int(cls[i]))), float(confs[i]), (x1, y1, x2, y2)))
        return out

    def reset_tracker(self) -> None:
        """Forget tracks (e.g. when the source changes)."""
        if self._model is not None:
            try:
                predictor = getattr(self._model, "predictor", None)
                trackers = getattr(predictor, "trackers", None) if predictor else None
                for t in trackers or []:
                    t.reset()
            except Exception:  # noqa: BLE001
                pass
