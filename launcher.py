"""Runs the app straight from a checkout without installing (python launcher.py)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from fasttracker.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
