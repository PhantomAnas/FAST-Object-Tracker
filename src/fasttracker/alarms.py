"""Alarm rules ("beep when 50 cars have passed") and the beep / sound actions."""

from __future__ import annotations

import os
import sys
import threading

from .counter import Totals
from .settings import AlarmRule


class AlarmEngine:
    """Decides when rules fire; the pipeline performs the actions."""

    def __init__(self, rules: list[AlarmRule]) -> None:
        self.rules = [r for r in rules if r.enabled]
        self._fired_at: dict[int, int] = {}       # rule index -> count it last fired at

    def reset(self) -> None:
        self._fired_at.clear()

    def check(self, totals: Totals) -> list[tuple[AlarmRule, int]]:
        fired = []
        for i, rule in enumerate(self.rules):
            count = totals.total(None if rule.cls == "*" else rule.cls)
            last = self._fired_at.get(i)
            if count < rule.count:
                continue
            if last is None:
                self._fired_at[i] = count
                fired.append((rule, count))
            elif rule.repeat and count >= last + rule.count:
                self._fired_at[i] = count
                fired.append((rule, count))
        return fired


# ----------------------------------------------------------------- actions

def beep(frequency: int = 1200, ms: int = 250) -> None:
    """A short attention beep, without blocking the caller."""
    def _run() -> None:
        if sys.platform == "win32":
            try:
                import winsound
                winsound.Beep(frequency, ms)
                return
            except Exception:  # noqa: BLE001
                pass
        sys.stdout.write("\a")
        sys.stdout.flush()
    threading.Thread(target=_run, daemon=True).start()


def play_sound(path: str) -> bool:
    """Play a .wav (Windows: winsound; elsewhere: a best-effort system player). Returns False if it could not."""
    if not path or not os.path.isfile(path):
        beep()
        return False
    if sys.platform == "win32":
        try:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            return True
        except Exception:  # noqa: BLE001
            beep()
            return False
    import shutil
    import subprocess
    for player in ("paplay", "aplay", "afplay", "ffplay"):
        exe = shutil.which(player)
        if exe:
            args = [exe, "-nodisp", "-autoexit", "-loglevel", "quiet", path] if player == "ffplay" else [exe, path]
            try:
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except OSError:
                continue
    beep()
    return False
