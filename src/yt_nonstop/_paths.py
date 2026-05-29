"""Path helpers for the staged package migration.

The legacy project still keeps many entrypoint modules in ``scripts/``.  New
business logic should live under ``src/yt_nonstop``; during the migration these
helpers keep compatibility with older script-only imports without requiring an
editable install.
"""

from __future__ import annotations

import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def scripts_dir() -> Path:
    return repo_root() / "scripts"


def ensure_scripts_on_path() -> None:
    path = str(scripts_dir())
    if path not in sys.path:
        sys.path.insert(0, path)
