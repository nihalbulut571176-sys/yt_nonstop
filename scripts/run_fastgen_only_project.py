"""Compatibility wrapper for the package orchestrator.

The production orchestration logic now lives in ``src/yt_nonstop/pipeline/orchestrator.py``.
This script remains callable for legacy workflows and shell snippets.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from yt_nonstop.pipeline.orchestrator import main  # noqa: E402


if __name__ == "__main__":
    main()
