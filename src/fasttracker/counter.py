"""Counting objects at a line.

Two ways to count, each switchable:
- cross: the object's centre moves from one side of the line to the other
  (counted once per crossing, with a direction).
- touch: the object's box touches the line (counted once per touch, i.e.
  again only after it has left the line).

Tracks are identified by the tracker's ids; the geometry is pure Python so
it is fully tested without a model.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

Point = tuple[float, float]
Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class Track:
    id: int
    name: str
    conf: float
    xyxy: Box

    @property
    def center(self) -> Point:
        x1, y1, x2, y2 = self.xyxy
        return (x1 + x2) / 2.0, (y1 + y2) / 2.0

    @property
    def bottom_center(self) -> Point:
        x1, _y1, x2, y2 = self.xyxy
        return (x1 + x2) / 2.0, y2


@dataclass(frozen=True)
class CountEvent:
    track_id: int
    name: str
    kind: str               # cross | touch
    direction: str          # in | out | "" (touch)
    frame: int
    timestamp: float


# ----------------------------------------------------------------- geometry

def side_of_line(p: Point, a: Point, b: Point) -> float:
    """Signed area: > 0 when p is left of a->b, < 0 right, 0 on the line."""
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def _orient(p: Point, q: Point, r: Point) -> int:
    v = side_of_line(r, p, q)
    return 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)


def _on_segment(p: Point, q: Point, r: Point) -> bool:
    return min(p[0], q[0]) - 1e-9 <= r[0] <= max(p[0], q[0]) + 1e-9 and \
        min(p[1], q[1]) - 1e-9 <= r[1] <= max(p[1], q[1]) + 1e-9


def segments_intersect(p1: Point, p2: Point, p3: Point, p4: Point) -> bool:
    o1, o2, o3, o4 = _orient(p1, p2, p3), _orient(p1, p2, p4), _orient(p3, p4, p1), _orient(p3, p4, p2)
    if o1 != o2 and o3 != o4:
        return True
    if o1 == 0 and _on_segment(p1, p2, p3):
        return True
    if o2 == 0 and _on_segment(p1, p2, p4):
        return True
    if o3 == 0 and _on_segment(p3, p4, p1):
        return True
    return o4 == 0 and _on_segment(p3, p4, p2)


def box_touches_line(box: Box, a: Point, b: Point) -> bool:
    """True when the line segment a-b passes through or touches the box."""
    x1, y1, x2, y2 = box
    x1, x2 = min(x1, x2), max(x1, x2)
    y1, y2 = min(y1, y2), max(y1, y2)
    inside = lambda p: x1 <= p[0] <= x2 and y1 <= p[1] <= y2  # noqa: E731
    if inside(a) or inside(b):
        return True
    edges = (((x1, y1), (x2, y1)), ((x2, y1), (x2, y2)), ((x2, y2), (x1, y2)), ((x1, y2), (x1, y1)))
    return any(segments_intersect(a, b, e1, e2) for e1, e2 in edges)


def point_segment_distance(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


# ------------------------------------------------------------------ counter

@dataclass
class _State:
    frames: int = 0
    last_side: int = 0          # -1 / +1, 0 = unknown yet
    touching: bool = False
    last_seen: int = 0
    name: str = ""


@dataclass
class Totals:
    by_class: dict[str, dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: {"in": 0, "out": 0, "touch": 0}))

    def add(self, name: str, key: str) -> None:
        self.by_class[name][key] += 1

    def total(self, name: str | None = None) -> int:
        names = [name] if name else list(self.by_class)
        return sum(sum(self.by_class[n].values()) for n in names if n in self.by_class)

    def as_dict(self) -> dict[str, dict[str, int]]:
        return {k: dict(v) for k, v in self.by_class.items()}

    def reset(self) -> None:
        self.by_class.clear()


class LineCounter:
    """Feed it the tracks of every frame; it returns the count events."""

    FORGET_AFTER = 90          # frames an id may vanish before its state is dropped

    def __init__(self, a: Point, b: Point, count_cross: bool = True, count_touch: bool = False,
                 direction: str = "both", min_frames: int = 2, anchor: str = "center") -> None:
        self.a, self.b = a, b
        self.count_cross, self.count_touch = count_cross, count_touch
        self.direction = direction
        self.min_frames = max(1, min_frames)
        self.anchor = anchor
        self.totals = Totals()
        self.events: list[CountEvent] = []
        self._state: dict[int, _State] = {}

    def set_line(self, a: Point, b: Point) -> None:
        """Move the line; side memory is cleared so nothing counts from the move itself."""
        self.a, self.b = a, b
        for st in self._state.values():
            st.last_side = 0
            st.touching = False

    def reset(self) -> None:
        self.totals.reset()
        self.events.clear()
        self._state.clear()

    def _point(self, t: Track) -> Point:
        return t.bottom_center if self.anchor == "bottom" else t.center

    def update(self, tracks: list[Track], frame: int, now: float | None = None) -> list[CountEvent]:
        now = time.time() if now is None else now
        out: list[CountEvent] = []
        for t in tracks:
            st = self._state.get(t.id)
            if st is None:
                st = self._state[t.id] = _State()
            st.frames += 1
            st.last_seen = frame
            st.name = t.name
            mature = st.frames >= self.min_frames
            if self.count_cross:
                v = side_of_line(self._point(t), self.a, self.b)
                side = 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)
                if side and st.last_side and side != st.last_side and mature:
                    direction = "in" if side > 0 else "out"
                    if self.direction == "both" or self.direction == direction:
                        ev = CountEvent(t.id, t.name, "cross", direction, frame, now)
                        out.append(ev)
                        self.totals.add(t.name, direction)
                if side:
                    st.last_side = side
            if self.count_touch:
                touching = box_touches_line(t.xyxy, self.a, self.b)
                if touching and not st.touching and mature:
                    ev = CountEvent(t.id, t.name, "touch", "", frame, now)
                    out.append(ev)
                    self.totals.add(t.name, "touch")
                st.touching = touching
        # Drop ids that have not been seen for a while.
        for tid in [tid for tid, st in self._state.items() if frame - st.last_seen > self.FORGET_AFTER]:
            del self._state[tid]
        self.events.extend(out)
        if len(self.events) > 5000:
            del self.events[:-5000]
        return out

    def active_ids(self) -> int:
        return len(self._state)
