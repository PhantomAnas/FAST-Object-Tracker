"""Reusable widgets: cards, buttons, segmented control, slider, file picker,
status light and the live video view with a draggable counting line."""

from __future__ import annotations

import os

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSlider, QVBoxLayout, QWidget,
)

from . import icons, theme


class Card(QFrame):
    def __init__(self, title: str | None = None, icon_name: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 12, 14, 14)
        self.body.setSpacing(10)
        if title:
            head = QHBoxLayout()
            head.setSpacing(8)
            if icon_name:
                ic = QLabel()
                ic.setPixmap(icons.pixmap(icon_name, 15, theme.ACCENT, dpr=self.devicePixelRatioF()))
                head.addWidget(ic)
            lbl = QLabel(title.upper())
            lbl.setObjectName("CardTitle")
            head.addWidget(lbl)
            head.addStretch(1)
            self.head = head
            self.body.addLayout(head)


def pill(text: str, icon_name: str | None = None, kind: str = "", tooltip: str = "") -> QPushButton:
    b = QPushButton(text)
    if icon_name:
        color = "#04211c" if kind in ("Go", "Primary") else (theme.RED if kind == "Danger" else theme.TEXT)
        b.setIcon(icons.icon(icon_name, color, filled=(icon_name == "play")))
        b.setIconSize(icons.ICON_SIZE)
    if kind:
        b.setObjectName(kind)
    if tooltip:
        b.setToolTip(tooltip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def round_button(icon_name: str, tooltip: str = "") -> QPushButton:
    b = QPushButton()
    b.setObjectName("Round")
    b.setIcon(icons.icon(icon_name))
    b.setIconSize(QSize(16, 16))
    b.setToolTip(tooltip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("Hint")
    lbl.setWordWrap(True)
    lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
    return lbl


def row(*widgets, stretch_last: bool = False) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    for i, w in enumerate(widgets):
        if isinstance(w, str):
            lbl = QLabel(w)
            lbl.setObjectName("Hint")
            lay.addWidget(lbl)
        else:
            lay.addWidget(w, 1 if (stretch_last and i == len(widgets) - 1) else 0)
    if not stretch_last:
        lay.addStretch(1)
    return lay


class Segmented(QFrame):
    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SegGroup")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for key, label in options:
            b = QPushButton(label)
            b.setObjectName("Seg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.group.addButton(b)
            lay.addWidget(b, 1)
            self._buttons[key] = b
            b.toggled.connect(lambda on, k=key: on and self.changed.emit(k))

    def set_value(self, key: str) -> None:
        if key in self._buttons:
            self._buttons[key].setChecked(True)

    def value(self) -> str:
        for k, b in self._buttons.items():
            if b.isChecked():
                return k
        return next(iter(self._buttons))


class LabeledSlider(QWidget):
    valueChanged = Signal(float)

    def __init__(self, caption: str, lo: float, hi: float, step: float, fmt: str = "{:.2f}",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.lo, self.step, self.fmt = lo, step, fmt
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        top = QHBoxLayout()
        self.caption = QLabel(caption)
        self.caption.setObjectName("Hint")
        self.value_lbl = QLabel()
        self.value_lbl.setObjectName("Mono")
        top.addWidget(self.caption)
        top.addStretch(1)
        top.addWidget(self.value_lbl)
        lay.addLayout(top)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, int(round((hi - lo) / step)))
        self.slider.valueChanged.connect(self._on_change)
        lay.addWidget(self.slider)

    def _on_change(self, raw: int) -> None:
        v = self.value()
        self.value_lbl.setText(self.fmt.format(v))
        self.valueChanged.emit(v)

    def value(self) -> float:
        return self.lo + self.slider.value() * self.step

    def set_value(self, v: float) -> None:
        self.slider.setValue(int(round((v - self.lo) / self.step)))
        self.value_lbl.setText(self.fmt.format(self.value()))


class FilePicker(QWidget):
    changed = Signal(str)

    def __init__(self, caption: str, icon_name: str, mode: str = "file", filter_: str = "",
                 placeholder: str = "None", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.mode, self.filter_, self.placeholder = mode, filter_, placeholder
        self._path = ""
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, 16, theme.MUTED_HEX if hasattr(theme, "MUTED_HEX") else "#9aa0a8", dpr=self.devicePixelRatioF()))
        lay.addWidget(ic)
        text = QVBoxLayout()
        text.setSpacing(0)
        self.cap = QLabel(caption)
        self.cap.setObjectName("Hint")
        self.name = QLabel(placeholder)
        self.name.setObjectName("Faint")
        self.name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        text.addWidget(self.cap)
        text.addWidget(self.name)
        lay.addLayout(text, 1)
        self.choose = pill("Choose")
        self.clear_btn = round_button("x", "Clear")
        self.clear_btn.setVisible(False)
        lay.addWidget(self.choose)
        lay.addWidget(self.clear_btn)
        self.choose.clicked.connect(self._pick)
        self.clear_btn.clicked.connect(lambda: self.set_path(""))

    def _pick(self) -> None:
        start = os.path.dirname(self._path) if self._path else os.path.expanduser("~")
        if self.mode == "dir":
            path = QFileDialog.getExistingDirectory(self, self.cap.text(), start)
        else:
            path, _ = QFileDialog.getOpenFileName(self, self.cap.text(), start, self.filter_)
        if path:
            self.set_path(os.path.normpath(path))

    def set_path(self, path: str) -> None:
        self._path = path or ""
        self.name.setText(os.path.basename(self._path) or self._path or self.placeholder)
        self.name.setObjectName("Hint" if self._path else "Faint")
        self.name.setToolTip(self._path)
        self.name.style().unpolish(self.name)
        self.name.style().polish(self.name)
        self.clear_btn.setVisible(bool(self._path))
        self.changed.emit(self._path)

    def path(self) -> str:
        return self._path


class StatusLight(QWidget):
    """A small dot with a caption: grey (idle), green (ok), red (problem)."""

    def __init__(self, caption: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state: str | None = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.dot = QLabel()
        self.dot.setFixedSize(10, 10)
        self.text = QLabel(caption)
        self.text.setObjectName("Hint")
        lay.addWidget(self.dot)
        lay.addWidget(self.text)
        self.set_state(None)

    def set_state(self, ok: bool | None) -> None:
        self.state = ok
        color = "rgba(255,255,255,0.18)" if ok is None else (theme.GREEN if ok else theme.RED)
        self.dot.setStyleSheet(f"background: {color}; border-radius: 5px;")


class VideoView(QWidget):
    """Shows frames (letterboxed) and lets the user drag the counting line.

    Line coordinates are normalised (0..1) so they survive resolution changes.
    `lineChanged(tuple)` emits (x1, y1, x2, y2) when a drag ends or moves.
    """

    lineChanged = Signal(tuple)
    HANDLE = 10

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._img: QImage | None = None
        self._aspect = 16 / 9
        self.line = [0.1, 0.5, 0.9, 0.5]
        self._drag: str | None = None      # "a" | "b" | "line"
        self._drag_from = QPointF()
        self._line_from: list[float] = []
        self.editable = True
        self.placeholder = "No video yet.  Choose a source and press Start.\nDrag the line's end points to place it."
        self.setMinimumSize(360, 220)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_frame(self, img: QImage) -> None:
        self._img = img
        if img.height():
            self._aspect = img.width() / img.height()
        self.update()

    def clear(self) -> None:
        self._img = None
        self.update()

    def set_line(self, line) -> None:
        self.line = [float(v) for v in line]
        self.update()

    # ------------------------------------------------------------- geometry
    def _frame_rect(self) -> QRectF:
        w, h = self.width(), self.height()
        if w / h > self._aspect:
            fh = h
            fw = h * self._aspect
        else:
            fw = w
            fh = w / self._aspect
        return QRectF((w - fw) / 2, (h - fh) / 2, fw, fh)

    def _to_px(self, nx: float, ny: float) -> QPointF:
        r = self._frame_rect()
        return QPointF(r.x() + nx * r.width(), r.y() + ny * r.height())

    def _to_norm(self, p: QPointF) -> tuple[float, float]:
        r = self._frame_rect()
        if r.width() <= 0 or r.height() <= 0:
            return 0.0, 0.0
        return (min(1.0, max(0.0, (p.x() - r.x()) / r.width())), min(1.0, max(0.0, (p.y() - r.y()) / r.height())))

    # ------------------------------------------------------------- painting
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(theme.FIELD))
        r = self._frame_rect()
        if self._img is not None:
            p.drawImage(r, self._img)
        else:
            p.fillRect(r, QColor("#15181c"))
            p.setPen(QColor(theme.FAINT.replace("rgba(230,232,236,0.36)", "#6b7078")))
            p.setPen(QColor(110, 115, 125))
            f = QFont()
            f.setPointSize(10)
            p.setFont(f)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.placeholder)
        a = self._to_px(self.line[0], self.line[1])
        b = self._to_px(self.line[2], self.line[3])
        live = self._img is not None and self._drag is None
        if not live:
            p.setPen(QPen(QColor(0, 0, 0, 160), 5))
            p.drawLine(a, b)
            p.setPen(QPen(QColor(theme.ACCENT), 2.5))
            p.drawLine(a, b)
        p.setBrush(QBrush(QColor(theme.ACCENT)))
        p.setPen(QPen(QColor(0, 0, 0, 180), 1))
        for pt in (a, b):
            p.drawEllipse(pt, 6, 6)
        if live:
            p.end()
            return
        # side labels (the pipeline draws its own on live frames)
        mx, my = (a.x() + b.x()) / 2, (a.y() + b.y()) / 2
        dx, dy = b.x() - a.x(), b.y() - a.y()
        n = (dx * dx + dy * dy) ** 0.5 or 1.0
        nx, ny = -dy / n, dx / n
        f = QFont()
        f.setPointSize(8)
        f.setBold(True)
        p.setFont(f)
        for sign, text in ((-1, "IN"), (1, "OUT")):
            cx, cy = mx + sign * nx * 20, my + sign * ny * 20
            p.setPen(QColor(0, 0, 0, 200))
            p.drawText(QRectF(cx - 20, cy - 9, 40, 18), Qt.AlignmentFlag.AlignCenter, text)
            p.setPen(QColor(theme.ACCENT))
            p.drawText(QRectF(cx - 21, cy - 10, 40, 18), Qt.AlignmentFlag.AlignCenter, text)
        p.end()

    # --------------------------------------------------------------- mouse
    def _hit(self, pos: QPointF) -> str | None:
        a = self._to_px(self.line[0], self.line[1])
        b = self._to_px(self.line[2], self.line[3])
        if (pos - a).manhattanLength() <= self.HANDLE * 1.6:
            return "a"
        if (pos - b).manhattanLength() <= self.HANDLE * 1.6:
            return "b"
        # distance to the segment
        ax, ay, bx, by = a.x(), a.y(), b.x(), b.y()
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((pos.x() - ax) * dx + (pos.y() - ay) * dy) / L))
        cx, cy = ax + t * dx, ay + t * dy
        if ((pos.x() - cx) ** 2 + (pos.y() - cy) ** 2) ** 0.5 <= 8:
            return "line"
        return None

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if not self.editable or e.button() != Qt.MouseButton.LeftButton:
            return
        self._drag = self._hit(e.position())
        self._drag_from = e.position()
        self._line_from = list(self.line)

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._drag is None:
            h = self._hit(e.position()) if self.editable else None
            self.setCursor(Qt.CursorShape.SizeAllCursor if h == "line" else
                           Qt.CursorShape.CrossCursor if h else Qt.CursorShape.ArrowCursor)
            return
        if self._drag in ("a", "b"):
            nx, ny = self._to_norm(e.position())
            i = 0 if self._drag == "a" else 2
            self.line[i], self.line[i + 1] = nx, ny
        else:
            r = self._frame_rect()
            d = e.position() - self._drag_from
            ddx, ddy = d.x() / max(1.0, r.width()), d.y() / max(1.0, r.height())
            cand = [self._line_from[0] + ddx, self._line_from[1] + ddy, self._line_from[2] + ddx, self._line_from[3] + ddy]
            if all(0.0 <= v <= 1.0 for v in cand):
                self.line = cand
        self.update()
        self.lineChanged.emit(tuple(self.line))

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if self._drag is not None:
            self._drag = None
            self.lineChanged.emit(tuple(self.line))
