from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WORKSPACE_ROOT = Path(r"C:\Users\MIKE\Documents\Codex\YT_visual")
DEFAULT_ENV_PATH = DEFAULT_REPO_ROOT / ".env"


def _split_paths(value: str) -> list[Path]:
    parts = [item.strip() for item in value.split(os.pathsep) if item.strip()]
    return [Path(item).resolve(strict=False) for item in parts]


def _load_dotenv_map(path: Path = DEFAULT_ENV_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value.strip().strip('"').strip("'")
    return values


def _env_value(values: dict[str, str], key: str, default: str = "") -> str:
    return os.environ.get(key) or values.get(key) or default


def _first_env_value(values: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = _env_value(values, key, "")
        if value:
            return value
    return ""


@dataclass(slots=True)
class WebConfig:
    repo_root: Path
    workspace_root: Path
    runtime_dir: Path
    allowed_project_roots: list[Path]
    default_poll_interval: float
    default_operator_username: str
    default_operator_password: str
    session_ttl_hours: int
    default_profile: str
    default_concurrency: int
    fastgen_api_url: str
    fastgen_model: str
    fastgen_api_key: str
    llm_provider_mode: str
    llm_provider_model: str
    llm_provider_api_key: str
    llm_provider_base_url: str
    google_api_key: str
    gemini_model: str

    @classmethod
    def from_env(cls) -> "WebConfig":
        env_values = _load_dotenv_map()
        repo_root = Path(_env_value(env_values, "YT_NONSTOP_REPO_ROOT", str(DEFAULT_REPO_ROOT))).resolve(strict=False)
        workspace_root = Path(_env_value(env_values, "YT_NONSTOP_WORKSPACE_ROOT", str(DEFAULT_WORKSPACE_ROOT))).resolve(strict=False)
        runtime_dir = Path(_env_value(env_values, "YT_NONSTOP_WEB_RUNTIME_DIR", str(repo_root / ".runtime" / "webstudio"))).resolve(strict=False)
        allowed_value = _env_value(env_values, "YT_NONSTOP_ALLOWED_PROJECT_ROOTS", "")
        allowed_roots = _split_paths(allowed_value) if allowed_value else [workspace_root]
        default_poll_interval = float(_env_value(env_values, "YT_NONSTOP_WEB_POLL_SECONDS", "2.5"))
        default_operator_username = _env_value(env_values, "YT_NONSTOP_STUDIO_USERNAME", "operator")
        default_operator_password = _env_value(env_values, "YT_NONSTOP_STUDIO_PASSWORD", "operator")
        session_ttl_hours = int(_env_value(env_values, "YT_NONSTOP_STUDIO_SESSION_TTL_HOURS", "12"))
        default_profile = _env_value(env_values, "YT_NONSTOP_WEB_DEFAULT_PROFILE", "no_vlm_production")
        default_concurrency = int(_env_value(env_values, "YT_NONSTOP_WEB_DEFAULT_CONCURRENCY", "10"))
        fastgen_api_url = _env_value(env_values, "FASTGEN_API_URL", "")
        fastgen_model = _env_value(env_values, "FASTGEN_MODEL", "")
        fastgen_api_key = _env_value(env_values, "FASTGEN_API_KEY", "")
        llm_provider_mode = _env_value(env_values, "YT_NONSTOP_LLM_PROVIDER_MODE", "")
        llm_provider_model = _env_value(env_values, "YT_NONSTOP_LLM_PROVIDER_MODEL", "")
        llm_provider_api_key = _env_value(env_values, "YT_NONSTOP_LLM_PROVIDER_API_KEY", "")
        llm_provider_base_url = _env_value(env_values, "YT_NONSTOP_LLM_PROVIDER_BASE_URL", "")
        google_api_key = _first_env_value(env_values, "GOOGLE_API_KEY", "GEMINI_API_KEY")
        gemini_model = _first_env_value(env_values, "GOOGLE_GEMINI_MODEL", "GEMINI_MODEL")
        return cls(
            repo_root=repo_root,
            workspace_root=workspace_root,
            runtime_dir=runtime_dir,
            allowed_project_roots=allowed_roots,
            default_poll_interval=default_poll_interval,
            default_operator_username=default_operator_username,
            default_operator_password=default_operator_password,
            session_ttl_hours=session_ttl_hours,
            default_profile=default_profile,
            default_concurrency=default_concurrency,
            fastgen_api_url=fastgen_api_url,
            fastgen_model=fastgen_model,
            fastgen_api_key=fastgen_api_key,
            llm_provider_mode=llm_provider_mode,
            llm_provider_model=llm_provider_model,
            llm_provider_api_key=llm_provider_api_key,
            llm_provider_base_url=llm_provider_base_url,
            google_api_key=google_api_key,
            gemini_model=gemini_model,
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
