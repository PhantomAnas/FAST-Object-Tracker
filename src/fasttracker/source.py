"""Video sources: webcams, video files, and network streams (RTSP/HTTP from
IP or CCTV cameras), all through OpenCV with reconnect handling."""

from __future__ import annotations

import os
import sys
import time

import cv2
import numpy as np

from .settings import TrackerSettings

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mpg", ".mpeg", ".wmv", ".ts", ".flv"}
STREAM_PREFIXES = ("rtsp://", "rtsps://", "http://", "https://", "udp://", "tcp://", "rtmp://")


class SourceError(Exception):
    pass


def describe_source(s: TrackerSettings) -> str:
    if s.source_kind == "webcam":
        return f"webcam {s.webcam_index}"
    if s.source_kind == "file":
        return os.path.basename(s.file_path) or "video file"
    return redact_url(s.url)


def redact_url(url: str) -> str:
    """Hide a password in rtsp://user:pass@host for logs and screenshots."""
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        creds, host = rest.rsplit("@", 1)
        if ":" in creds:
            creds = creds.split(":", 1)[0] + ":****"
        return f"{scheme}://{creds}@{host}"
    return url


def source_target(s: TrackerSettings):
    if s.source_kind == "webcam":
        return int(s.webcam_index)
    if s.source_kind == "file":
        return s.file_path
    url = s.url.strip()
    head = url.split(":")[0]
    if not url.lower().startswith(STREAM_PREFIXES) and ":" in url and len(head) > 1 and "/" not in head and "\\" not in head:
        # "192.168.1.64:554/stream" -> assume rtsp
        url = "rtsp://" + url
    return url


def list_webcams(max_index: int = 6) -> list[int]:
    """Indices that open (each probe takes a moment; call from a worker thread)."""
    found = []
    for i in range(max_index):
        cap = _open(i)
        if cap.isOpened():
            ok, _ = cap.read()
            if ok:
                found.append(i)
        cap.release()
    return found


def _open(target) -> cv2.VideoCapture:
    if isinstance(target, int) and sys.platform == "win32":
        return cv2.VideoCapture(target, cv2.CAP_DSHOW)
    if isinstance(target, str) and target.lower().startswith("rtsp"):
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;5000000")
        return cv2.VideoCapture(target, cv2.CAP_FFMPEG)
    return cv2.VideoCapture(target)


class VideoSource:
    """Opens the configured source; `read()` returns a frame or None at the end."""

    def __init__(self, s: TrackerSettings) -> None:
        self.s = s
        self.target = source_target(s)
        self.cap: cv2.VideoCapture | None = None
        self.is_file = s.source_kind == "file"
        self.is_stream = s.source_kind == "url"
        self.fps = 0.0
        self.width = 0
        self.height = 0
        self.frame_count = 0
        self.failures = 0
        self.reconnects = 0

    def open(self) -> "VideoSource":
        if self.is_file and not os.path.isfile(self.target):
            raise SourceError(f"video file not found: {self.target}")
        self.cap = _open(self.target)
        if not self.cap.isOpened():
            self.cap.release()
            self.cap = None
            if self.s.source_kind == "webcam":
                raise SourceError(f"webcam {self.target} could not be opened (in use by another app, or not connected?)")
            if self.is_stream:
                raise SourceError(f"could not connect to {redact_url(str(self.target))} (check the URL, user/password and that the camera is reachable)")
            raise SourceError(f"could not open {self.target}")
        self.fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 0.0)
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) if self.is_file else 0
        if self.is_stream:
            try:
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:  # noqa: BLE001
                pass
        return self

    def read(self) -> np.ndarray | None:
        """Next frame; loops files when asked; reconnects streams; None = finished."""
        if self.cap is None:
            return None
        ok, frame = self.cap.read()
        if ok and frame is not None:
            self.failures = 0
            return frame
        if self.is_file:
            if self.s.loop_file and self.frame_count > 1:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self.cap.read()
                return frame if ok else None
            return None
        self.failures += 1
        if self.failures < 30:
            time.sleep(0.02)
            return self.read_retry()
        return None

    def read_retry(self) -> np.ndarray | None:
        assert self.cap is not None
        ok, frame = self.cap.read()
        if ok and frame is not None:
            self.failures = 0
            return frame
        return None if self.failures >= 30 else self.read()

    def reconnect(self) -> bool:
        """Try to reopen a dropped stream or webcam."""
        self.release()
        time.sleep(min(5.0, 0.5 * (self.reconnects + 1)))
        self.reconnects += 1
        try:
            self.open()
        except SourceError:
            return False
        return True

    def release(self) -> None:
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:  # noqa: BLE001
                pass
            self.cap = None

    def __enter__(self) -> "VideoSource":
        return self.open()

    def __exit__(self, *exc) -> None:
        self.release()
