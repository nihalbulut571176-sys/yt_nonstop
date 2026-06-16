from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WORKSPACE_ROOT = Path(r"C:\Users\MIKE\Documents\Codex\YT_visual")


def _split_paths(value: str) -> list[Path]:
    parts = [item.strip() for item in value.split(os.pathsep) if item.strip()]
    return [Path(item).resolve(strict=False) for item in parts]


@dataclass(slots=True)
class WebConfig:
    repo_root: Path
    workspace_root: Path
    runtime_dir: Path
    allowed_project_roots: list[Path]
    default_poll_interval: float

    @classmethod
    def from_env(cls) -> "WebConfig":
        repo_root = Path(os.environ.get("YT_NONSTOP_REPO_ROOT", str(DEFAULT_REPO_ROOT))).resolve(strict=False)
        workspace_root = Path(os.environ.get("YT_NONSTOP_WORKSPACE_ROOT", str(DEFAULT_WORKSPACE_ROOT))).resolve(strict=False)
        runtime_dir = Path(os.environ.get("YT_NONSTOP_WEB_RUNTIME_DIR", str(repo_root / ".runtime" / "webstudio"))).resolve(strict=False)
        allowed_value = os.environ.get("YT_NONSTOP_ALLOWED_PROJECT_ROOTS", "")
        allowed_roots = _split_paths(allowed_value) if allowed_value else [workspace_root]
        default_poll_interval = float(os.environ.get("YT_NONSTOP_WEB_POLL_SECONDS", "2.5"))
        return cls(
            repo_root=repo_root,
            workspace_root=workspace_root,
            runtime_dir=runtime_dir,
            allowed_project_roots=allowed_roots,
            default_poll_interval=default_poll_interval,
        )

    def ensure_runtime_dirs(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        (self.runtime_dir / "logs").mkdir(parents=True, exist_ok=True)

    def project_allowed(self, path: Path) -> bool:
        candidate = path.resolve(strict=False)
        return any(self._is_within(candidate, root) for root in self.allowed_project_roots)

    @staticmethod
    def _is_within(candidate: Path, root: Path) -> bool:
        try:
            candidate.relative_to(root.resolve(strict=False))
            return True
        except ValueError:
            return False
