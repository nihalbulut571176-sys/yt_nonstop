"""Compatibility wrapper for VLM semantic QC providers.

Business logic lives in ``src/yt_nonstop/providers/vlm_semantic_qc_provider.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from yt_nonstop.providers.vlm_semantic_qc_provider import *  # noqa: F401,F403,E402
