from fasttracker.counter import LineCounter, Track, box_touches_line, point_segment_distance, segments_intersect, side_of_line

A, B = (0.0, 100.0), (200.0, 100.0)      # horizontal line at y=100


def tr(tid, y, name="person", x=50.0, size=20.0):
    return Track(tid, name, 0.9, (x - size / 2, y - size / 2, x + size / 2, y + size / 2))


def test_side_of_line_signs():
    assert side_of_line((50, 50), A, B) < 0
    assert side_of_line((50, 150), A, B) > 0
    assert side_of_line((50, 100), A, B) == 0


def test_segments_intersect():
    assert segments_intersect((0, 0), (10, 10), (0, 10), (10, 0))
    assert not segments_intersect((0, 0), (10, 0), (0, 5), (10, 5))
    assert segments_intersect((0, 0), (10, 0), (5, 0), (5, 5))     # touching endpoint


def test_box_touches_line():
    assert box_touches_line((40, 90, 60, 110), A, B)
    assert not box_touches_line((40, 110, 60, 130), A, B)
    assert box_touches_line((40, 90, 60, 110), (50, 0), (50, 200))   # vertical line through the box
    assert box_touches_line((0, 0, 300, 300), A, B)                  # line fully inside the box


def test_point_segment_distance():
    assert point_segment_distance((50, 120), A, B) == 20
    assert point_segment_distance((-30, 100), A, B) == 30


def test_cross_counts_once_with_direction():
    c = LineCounter(A, B, count_cross=True, count_touch=False, min_frames=1)
    for f, y in enumerate([50, 80, 95, 105, 130, 160], start=1):
        c.update([tr(1, y)], f)
    assert c.totals.total("person") == 1
    assert c.totals.as_dict()["person"]["in"] == 1
    assert c.events[0].direction == "in" and c.events[0].kind == "cross"
    # coming back counts as out
    for f, y in enumerate([130, 95, 60], start=10):
        c.update([tr(1, y)], f)
    assert c.totals.as_dict()["person"] == {"in": 1, "out": 1, "touch": 0}


def test_direction_filter():
    c = LineCounter(A, B, direction="out", min_frames=1)
    for f, y in enumerate([50, 150, 50, 150], start=1):
        c.update([tr(1, y)], f)
    assert c.totals.as_dict()["person"] == {"in": 0, "out": 1, "touch": 0}


def test_min_frames_prevents_counting_on_first_sighting():
    c = LineCounter(A, B, min_frames=3)
    c.update([tr(1, 80)], 1)
    c.update([tr(1, 120)], 2)       # crossed, but only seen twice
    assert c.totals.total() == 0
    c.update([tr(1, 80)], 3)        # third frame: now mature, crosses back
    assert c.totals.total() == 1


def test_jitter_on_the_line_does_not_double_count():
    c = LineCounter(A, B, min_frames=1)
    for f, y in enumerate([90, 100, 100, 100, 110], start=1):   # sits exactly on the line a while
        c.update([tr(1, y)], f)
    assert c.totals.total() == 1


def test_touch_counts_once_per_visit():
    c = LineCounter(A, B, count_cross=False, count_touch=True, min_frames=1)
    for f, y in enumerate([50, 95, 100, 105, 150, 95, 150], start=1):
        c.update([tr(1, y)], f)
    assert c.totals.as_dict()["person"] == {"in": 0, "out": 0, "touch": 2}


def test_cross_and_touch_together():
    c = LineCounter(A, B, count_cross=True, count_touch=True, min_frames=1)
    for f, y in enumerate([50, 95, 105, 150], start=1):
        c.update([tr(1, y)], f)
    assert c.totals.as_dict()["person"] == {"in": 1, "out": 0, "touch": 1}
    assert c.totals.total() == 2


def test_multiple_classes_and_ids():
    c = LineCounter(A, B, min_frames=1)
    c.update([tr(1, 50, "car"), tr(2, 50, "person"), tr(3, 150, "car")], 1)
    c.update([tr(1, 150, "car"), tr(2, 150, "person"), tr(3, 50, "car")], 2)
    d = c.totals.as_dict()
    assert d["car"] == {"in": 2, "out": 0, "touch": 0} or d["car"]["in"] + d["car"]["out"] == 2
    assert c.totals.total("person") == 1
    assert c.totals.total() == 3


def test_set_line_does_not_create_phantom_counts():
    c = LineCounter(A, B, min_frames=1)
    c.update([tr(1, 50)], 1)
    c.set_line((0, 20), (200, 20))        # the object is now on the other side of the new line
    c.update([tr(1, 50)], 2)
    assert c.totals.total() == 0
    c.update([tr(1, 10)], 3)
    assert c.totals.total() == 1


def test_forget_stale_ids_and_reset():
    c = LineCounter(A, B, min_frames=1)
    c.update([tr(1, 50)], 1)
    assert c.active_ids() == 1
    c.update([], 1 + LineCounter.FORGET_AFTER + 1)
    assert c.active_ids() == 0
    c.update([tr(2, 50)], 200)
    c.update([tr(2, 150)], 201)
    c.reset()
    assert c.totals.total() == 0 and not c.events and c.active_ids() == 0


def test_vertical_line_in_out():
    c = LineCounter((100, 0), (100, 200), min_frames=1)   # a->b points down; IN is left side... check consistency
    c.update([tr(1, 100, x=50)], 1)
    c.update([tr(1, 100, x=150)], 2)
    assert c.totals.total() == 1
    first = c.events[0].direction
    c.update([tr(1, 100, x=50)], 3)
    assert c.events[1].direction != first
