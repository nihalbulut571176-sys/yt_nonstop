from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from yt_nonstop.webapi.models import ArtifactEntry, FilePreview, ReviewPayload, TimelinePayload


ARTIFACT_DIRS = (
    ("images", "images"),
    ("final_images", "final_images"),
    ("output", "output"),
    ("renders", "renders"),
    ("work", "work"),
    ("reports", "reports"),
    ("prompts", "prompts"),
    ("qc", "qc"),
    ("exports", "exports"),
)

TEXT_SUFFIXES = {".txt", ".md", ".json", ".jsonl", ".csv", ".log", ".srt"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".webm"}


def _iso_from_ts(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _preview_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in VIDEO_SUFFIXES:
        return "video"
    if suffix in TEXT_SUFFIXES:
        return "text"
    return "binary"


def list_artifacts(project_root: Path) -> list[ArtifactEntry]:
    entries: list[ArtifactEntry] = []
    for label, relative in ARTIFACT_DIRS:
        base = project_root / relative
        if not base.exists():
            continue
        for path in sorted((item for item in base.rglob("*") if item.is_file()), key=lambda item: str(item).lower()):
            stat = path.stat()
            entries.append(
                ArtifactEntry(
                    type=label,
                    label=str(path.relative_to(project_root)),
                    path=str(path.resolve(strict=False)),
                    size=stat.st_size,
                    modified_at=_iso_from_ts(stat.st_mtime),
                    preview_kind=_preview_kind(path),
                )
            )
    return entries


def preview_file(path: Path, *, max_lines: int = 120) -> FilePreview:
    preview_kind = _preview_kind(path)
    if preview_kind != "text":
        return FilePreview(path=str(path), preview_kind=preview_kind)
    content = path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()[:max_lines]
    return FilePreview(path=str(path), preview_kind=preview_kind, content="\n".join(lines), lines=lines)


def _read_json_or_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("rows", "timeline", "selected_images", "beats", "images", "frames"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    return []


def load_timeline(project_id: str, project_root: Path, project_json: Path | None = None) -> TimelinePayload:
    candidates = [
        project_root / "renders" / "slideshow_timeline.json",
        project_root / "exports" / "edit_timeline.csv",
        project_root / "work" / "timeline.csv",
    ]
    if project_json and project_json.exists():
        candidates.insert(0, project_root / "renders" / "edit_decision_list.json")
    for candidate in candidates:
        rows = _read_json_or_csv_rows(candidate)
        if rows:
            return TimelinePayload(project_id=project_id, source=str(candidate.resolve(strict=False)), rows=rows)
    return TimelinePayload(project_id=project_id, rows=[])


def load_review(project_id: str, project_root: Path, project_json: Path | None = None) -> ReviewPayload:
    candidates = [
        project_root / "qc" / "review_applied_manifest.json",
        project_root / "qc" / "selected_images_manifest.json",
        project_root / "work" / "review_sheet.csv",
        project_root / "reports" / "qc_report.md",
    ]
    for candidate in candidates:
        rows = _read_json_or_csv_rows(candidate)
        if rows:
            return ReviewPayload(project_id=project_id, source=str(candidate.resolve(strict=False)), rows=rows)
    return ReviewPayload(project_id=project_id, rows=[])
