"""Compatibility wrapper for runtime state helpers.

Business logic lives in ``src/yt_nonstop/state/pipeline_state.py``.  This file is
kept as a thin script-era import shim so older modules can still do
``from pipeline_state import ...`` during the packaging migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from yt_nonstop.state.pipeline_state import *  # noqa: F401,F403,E402
