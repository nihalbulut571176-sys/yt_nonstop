"""Thin CLI wrapper for the production dashboard.

Business logic lives in ``src/yt_nonstop/pipeline/project_status.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from yt_nonstop.pipeline.project_status import main  # noqa: E402


if __name__ == "__main__":
    main()
