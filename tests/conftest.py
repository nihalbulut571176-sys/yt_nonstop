"""Test import bootstrap for the staged src/ package migration."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "scripts"):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)
