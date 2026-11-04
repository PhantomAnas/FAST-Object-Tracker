"""Optional serial output for an Arduino (or any USB-serial board): a short
message is written on every count or alarm, so the board can pulse a relay,
a light, a counter display, a printer trigger...  See docs/arduino.md."""

from __future__ import annotations

import threading
import time


class SerialError(Exception):
    pass


def serial_available() -> bool:
    try:
        import serial  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def list_ports() -> list[tuple[str, str]]:
    """[(device, description)] of the serial ports on this machine."""
    try:
        from serial.tools import list_ports as lp
    except Exception:  # noqa: BLE001
        return []
    out = []
    for p in lp.comports():
        out.append((p.device, p.description or ""))
    return sorted(out)


USB_HINTS = ("usb", "arduino", "ch340", "cp210", "ftdi", "wch", "silicon labs")


def auto_port(ports: list[tuple[str, str]] | None = None) -> str:
    """The first port that looks like a USB serial board, else the first port, else ''."""
    ports = list_ports() if ports is None else ports
    for dev, desc in ports:
        if any(h in desc.lower() for h in USB_HINTS):
            return dev
    return ports[0][0] if ports else ""


class SerialLink:
    """Thread-safe writer with lazy reconnect.  Never raises from `pulse`."""

    def __init__(self, port: str = "", baud: int = 9600, message: bytes = b"Go\r") -> None:
        self.port_setting = port
        self.baud = baud
        self.message = message
        self._ser = None
        self._lock = threading.Lock()
        self.last_error = ""
        self.sent = 0
        self.port = ""

    def open(self) -> str:
        """Open the configured (or auto-detected) port; returns the port name."""
        if not serial_available():
            raise SerialError("pyserial is not installed (pip install pyserial)")
        import serial
        port = self.port_setting or auto_port()
        if not port:
            raise SerialError("no serial port found: plug the board in (and install its USB driver)")
        with self._lock:
            self.close()
            try:
                self._ser = serial.Serial(port=port, baudrate=self.baud, timeout=1, write_timeout=1)
            except Exception as exc:  # noqa: BLE001
                self._ser = None
                raise SerialError(f"could not open {port}: {exc}") from exc
            self.port = port
            self.last_error = ""
        return port

    @property
    def is_open(self) -> bool:
        return self._ser is not None and bool(getattr(self._ser, "is_open", False))

    def pulse(self, message: bytes | None = None) -> bool:
        """Write the message (in the caller's thread, under a lock). False on failure."""
        data = self.message if message is None else message
        with self._lock:
            if self._ser is None:
                return False
            try:
                self._ser.write(data)
                self._ser.flush()
                self.sent += 1
                return True
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)
                try:
                    self._ser.close()
                except Exception:  # noqa: BLE001
                    pass
                self._ser = None
                return False

    def pulse_async(self, message: bytes | None = None) -> None:
        threading.Thread(target=self.pulse, args=(message,), daemon=True).start()

    def try_reconnect(self, min_interval: float = 3.0) -> bool:
        now = time.time()
        if now - getattr(self, "_last_try", 0.0) < min_interval:
            return False
        self._last_try = now
        try:
            self.open()
            return True
        except SerialError as exc:
            self.last_error = str(exc)
            return False

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:  # noqa: BLE001
                pass
            self._ser = None
