import json

import pytest

from fasttracker import cli
from fasttracker.settings import AlarmRule, TrackerSettings
from fasttracker.source import redact_url, source_target


def test_defaults_validate(tmp_path):
    s = TrackerSettings()
    assert s.validate() == []
    s.save(str(tmp_path / "s.json"))
    back = TrackerSettings.load(str(tmp_path / "s.json"))
    assert back == s


def test_validate_reports_problems():
    s = TrackerSettings(source_kind="file", file_path="nope.mp4", model="missing.pt", conf=2, line=(0, 0, 2, 0),
                        count_cross=False, count_touch=False, alarms=[AlarmRule(count=0, action="x")])
    msgs = " ".join(s.validate())
    for word in ("video file", "model file", "confidence", "line", "at least one", "alarm 1"):
        assert word in msgs


def test_from_dict_ignores_junk_and_repairs():
    s = TrackerSettings.from_dict({"line": [2, -1, 0.5, "0.5"], "alarms": [{"cls": "car", "count": 3, "bogus": 1}, 5],
                                   "classes": "person", "unknown": True})
    assert s.line == (1.0, 0.0, 0.5, 0.5)
    assert len(s.alarms) == 1 and s.alarms[0].cls == "car"
    assert s.classes == ["person"]


def test_corrupt_file_gives_defaults(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{not json", encoding="utf-8")
    assert TrackerSettings.load(str(p)) == TrackerSettings()


def test_serial_bytes_escapes():
    assert TrackerSettings(serial_message="Go\\r").serial_bytes == b"Go\r"
    assert TrackerSettings(serial_message="A\\n").serial_bytes == b"A\n"


def test_redact_and_target():
    assert redact_url("rtsp://admin:secret@10.0.0.5:554/stream") == "rtsp://admin:****@10.0.0.5:554/stream"
    assert redact_url("http://10.0.0.5/video") == "http://10.0.0.5/video"
    assert source_target(TrackerSettings(source_kind="url", url="10.0.0.5:554/live")) == "rtsp://10.0.0.5:554/live"
    assert source_target(TrackerSettings(source_kind="webcam", webcam_index=2)) == 2


def test_cli_apply_args(tmp_path):
    vid = tmp_path / "v.mp4"
    vid.write_bytes(b"0")
    a = cli.build_parser().parse_args(["--source", str(vid), "--classes", "car, truck", "--line", "0,0.5,1,0.5",
                                       "--touch", "on", "--cross", "off", "--alarm", "car:5:serial:repeat",
                                       "--serial", "--serial-message", "P\\n", "--conf", "0.6"])
    s = cli.apply_args(TrackerSettings(), a)
    assert s.source_kind == "file" and s.file_path == str(vid)
    assert s.classes == ["car", "truck"] and s.line == (0, 0.5, 1, 0.5)
    assert s.count_touch and not s.count_cross
    assert s.alarms[0] == AlarmRule(cls="car", count=5, action="serial", repeat=True)
    assert s.serial_enabled and s.serial_bytes == b"P\n" and s.conf == 0.6
    a = cli.build_parser().parse_args(["--source", "1", "--classes", "all"])
    s = cli.apply_args(TrackerSettings(), a)
    assert s.source_kind == "webcam" and s.webcam_index == 1 and s.classes == []
    a = cli.build_parser().parse_args(["--source", "rtsp://cam/live"])
    assert cli.apply_args(TrackerSettings(), a).source_kind == "url"


def test_cli_bad_alarm():
    with pytest.raises(ValueError):
        cli.parse_alarm("person")


def test_cli_validation_error_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(TrackerSettings, "load", classmethod(lambda cls: TrackerSettings()))
    assert cli.main(["--source", str(tmp_path / "missing.mp4")]) == 2
    assert cli.main(["--source", "0", "--line", "1,2"]) == 2


def test_cli_save_settings(tmp_path, monkeypatch):
    path = tmp_path / "cfg.json"
    monkeypatch.setattr("fasttracker.settings.config_path", lambda: str(path))
    monkeypatch.setattr("fasttracker.cli.config_path", lambda: str(path))
    assert cli.main(["--classes", "cat", "--save-settings"]) == 0
    assert json.loads(path.read_text())["classes"] == ["cat"]
