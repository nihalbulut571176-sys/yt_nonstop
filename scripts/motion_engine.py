"""Compatibility wrapper for render motion helpers.

Business logic lives in ``src/yt_nonstop/render/motion_engine.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from yt_nonstop.render.motion_engine import *  # noqa: F401,F403,E402
