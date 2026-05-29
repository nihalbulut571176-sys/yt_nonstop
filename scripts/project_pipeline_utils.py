from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from yt_nonstop.pipeline.artifact_paths import (  # noqa: E402
    STAGE_ALIASES,
    STAGE_SEQUENCE,
    V2_STAGE_SEQUENCE,
    normalize_stage_name,
    stage_index,
)
from yt_nonstop.pipeline.project_config import (  # noqa: E402
    append_event,
    append_log,
    load_project,
    mark_stage,
    project_local_path,
    save_project,
)
from yt_nonstop.utils.json_io import append_text, ensure_parent, iso_now, load_json, save_json  # noqa: E402

__all__ = [
    "STAGE_ALIASES",
    "STAGE_SEQUENCE",
    "V2_STAGE_SEQUENCE",
    "append_event",
    "append_log",
    "append_text",
    "ensure_parent",
    "iso_now",
    "load_json",
    "load_project",
    "mark_stage",
    "normalize_stage_name",
    "project_local_path",
    "save_json",
    "save_project",
    "stage_index",
]
