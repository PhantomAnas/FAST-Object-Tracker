from fasttracker.alarms import AlarmEngine
from fasttracker.counter import Totals
from fasttracker.serial_link import SerialLink, auto_port
from fasttracker.settings import AlarmRule


def totals(**counts):
    t = Totals()
    for name, n in counts.items():
        for _ in range(n):
            t.add(name, "in")
    return t


def test_alarm_fires_once_at_threshold():
    eng = AlarmEngine([AlarmRule(cls="person", count=3, action="beep")])
    assert eng.check(totals(person=2)) == []
    fired = eng.check(totals(person=3))
    assert len(fired) == 1 and fired[0][1] == 3
    assert eng.check(totals(person=4)) == []
    assert eng.check(totals(person=99)) == []


def test_alarm_repeat_every_n():
    eng = AlarmEngine([AlarmRule(cls="*", count=2, repeat=True)])
    assert len(eng.check(totals(car=2))) == 1
    assert eng.check(totals(car=3)) == []
    assert len(eng.check(totals(car=4, person=0))) == 1
    assert len(eng.check(totals(car=4, person=2))) == 1    # "*" counts every class


def test_disabled_rule_ignored_and_reset():
    eng = AlarmEngine([AlarmRule(cls="person", count=1, enabled=False), AlarmRule(cls="person", count=1)])
    assert len(eng.check(totals(person=1))) == 1
    eng.reset()
    assert len(eng.check(totals(person=1))) == 1


def test_describe():
    assert AlarmRule(cls="*", count=5, action="serial", repeat=True).describe() == "any object every 5: serial"


def test_auto_port_prefers_usb_boards():
    ports = [("COM1", "Communications Port"), ("COM7", "USB-SERIAL CH340 (COM7)")]
    assert auto_port(ports) == "COM7"
    assert auto_port([("COM1", "Communications Port")]) == "COM1"
    assert auto_port([]) == ""


class FakeSerial:
    is_open = True

    def __init__(self, fail=False):
        self.written = []
        self.fail = fail

    def write(self, data):
        if self.fail:
            raise OSError("unplugged")
        self.written.append(data)

    def flush(self):
        pass

    def close(self):
        self.is_open = False


def test_serial_pulse_without_port_is_false():
    link = SerialLink("COM99", 9600, b"Go\r")
    assert link.pulse() is False and link.sent == 0


def test_serial_pulse_writes_and_recovers_from_errors():
    link = SerialLink()
    fake = FakeSerial()
    link._ser = fake
    assert link.pulse() and fake.written == [b"Go\r"] and link.sent == 1
    assert link.pulse(b"X\n") and fake.written[-1] == b"X\n"
    link._ser = FakeSerial(fail=True)
    assert link.pulse() is False
    assert link.last_error == "unplugged" and not link.is_open
