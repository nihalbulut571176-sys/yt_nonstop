from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ALLOWED_LLM_PROVIDER_MODES = {"disabled", "file", "command", "http", "openai_compatible"}
GENERAL_LLM_ENV_PREFIX = "YT_NONSTOP_LLM_PROVIDER"
ENV_PATH = Path(__file__).resolve().parents[3] / ".env"

DEFAULT_STAGE_CONFIG: dict[str, dict[str, Any]] = {
    "author_narration_beats": {
        "alias_prefixes": ["YT_NONSTOP_BEAT_AUTHORING"],
        "project_paths": [("planning", "narration_beats_llm")],
    },
    "author_visual_allocation_plan": {
        "alias_prefixes": ["YT_NONSTOP_VISUAL_ALLOCATOR"],
        "project_paths": [("planning", "visual_allocation_llm")],
    },
    "auto_author_llm_prompts": {
        "alias_prefixes": ["YT_NONSTOP_PROMPT_AUTHORING"],
        "project_paths": [("prompts", "prompt_authoring_llm")],
    },
    "repair_failed_prompts": {
        "alias_prefixes": ["YT_NONSTOP_PROMPT_REPAIR"],
        "project_paths": [("prompts", "prompt_repair_llm"), ("qc", "prompt_repair_llm")],
    },
}


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def _int_from_any(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_from_any(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_provider_mode(value: Any) -> str:
    text = clean_text(value).lower().replace("-", "_")
    aliases = {
        "off": "disabled",
        "none": "disabled",
        "heuristic": "disabled",
        "openai": "openai_compatible",
        "chat_completions": "openai_compatible",
    }
    resolved = aliases.get(text, text or "disabled")
    if resolved == "external":
        resolved = "openai_compatible"
    if resolved not in ALLOWED_LLM_PROVIDER_MODES:
        raise ValueError(f"Unsupported LLM provider mode `{resolved}`")
    return resolved


@dataclass
class LLMProviderConfig:
    provider_mode: str
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    command: str | list[str] | None = None
    input_json_path: str | None = None
    timeout_seconds: int = 120
    max_tokens: int = 7000
    stage_name: str = ""
    env_prefix: str = GENERAL_LLM_ENV_PREFIX
    temperature: float = 0.2
    log_dir: str | None = None

    @property
    def mode(self) -> str:
        return self.provider_mode

    @mode.setter
    def mode(self, value: str) -> None:
        self.provider_mode = value

    @property
    def endpoint_url(self) -> str | None:
        return self.base_url

    @endpoint_url.setter
    def endpoint_url(self, value: str | None) -> None:
        self.base_url = value


def _load_stage_raw_config(project: dict[str, Any], *, stage_name: str) -> tuple[dict[str, Any], list[str]]:
    defaults = DEFAULT_STAGE_CONFIG.get(stage_name, {})
    merged: dict[str, Any] = {}
    for section, key in defaults.get("project_paths", []):
        value = project.get(section, {}).get(key)
        if isinstance(value, dict):
            merged.update(value)
    shared = project.get("providers", {}).get("llm_provider")
    if isinstance(shared, dict):
        merged = {**shared, **merged}
    return merged, list(defaults.get("alias_prefixes", []))


def _env_value(field: str, *, alias_prefixes: list[str]) -> str | None:
    suffixes = [field]
    if field == "MODE":
        suffixes.append("PROVIDER")
    for prefix in alias_prefixes + [GENERAL_LLM_ENV_PREFIX]:
        for suffix in suffixes:
            value = os.environ.get(f"{prefix}_{suffix}")
            if value not in {None, ""}:
                return value
            dotenv_value = _dotenv_value(f"{prefix}_{suffix}")
            if dotenv_value not in {None, ""}:
                return dotenv_value
    return None


def _load_dotenv_map() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = value.strip()
    return values


def _dotenv_value(key: str) -> str | None:
    return _load_dotenv_map().get(key)


def provider_from_project(
    project: dict[str, Any],
    *,
    stage_name: str,
    override_mode: str | None = None,
    input_json_path: str | None = None,
) -> LLMProviderConfig:
    raw, alias_prefixes = _load_stage_raw_config(project, stage_name=stage_name)

    configured_external_mode = (
        _env_value("MODE", alias_prefixes=alias_prefixes)
        or raw.get("mode")
        or raw.get("provider")
        or "openai_compatible"
    )
    if input_json_path:
        resolved_mode = "file"
    elif clean_text(override_mode).lower() == "external":
        resolved_mode = normalize_provider_mode(configured_external_mode)
    else:
        resolved_mode = normalize_provider_mode(
            override_mode
            or _env_value("MODE", alias_prefixes=alias_prefixes)
            or raw.get("mode")
            or raw.get("provider")
            or "disabled"
        )

    project_root = Path(str(project.get("meta", {}).get("project_root") or Path.cwd()))
    return LLMProviderConfig(
        provider_mode=resolved_mode,
        model=_env_value("MODEL", alias_prefixes=alias_prefixes) or raw.get("model"),
        api_key=_env_value("API_KEY", alias_prefixes=alias_prefixes) or raw.get("api_key"),
        base_url=(
            _env_value("BASE_URL", alias_prefixes=alias_prefixes)
            or _env_value("URL", alias_prefixes=alias_prefixes)
            or raw.get("base_url")
            or raw.get("endpoint_url")
        ),
        command=_env_value("COMMAND", alias_prefixes=alias_prefixes) or _env_value("CMD", alias_prefixes=alias_prefixes) or raw.get("command"),
        input_json_path=input_json_path or _env_value("INPUT_JSON", alias_prefixes=alias_prefixes) or raw.get("input_json_path"),
        timeout_seconds=_int_from_any(
            _env_value("TIMEOUT_SECONDS", alias_prefixes=alias_prefixes) or raw.get("timeout_seconds"),
            120,
        ),
        max_tokens=_int_from_any(
            _env_value("MAX_TOKENS", alias_prefixes=alias_prefixes) or raw.get("max_tokens"),
            7000,
        ),
        stage_name=stage_name,
        env_prefix=alias_prefixes[0] if alias_prefixes else GENERAL_LLM_ENV_PREFIX,
        temperature=_float_from_any(
            _env_value("TEMPERATURE", alias_prefixes=alias_prefixes) or raw.get("temperature"),
            0.2,
        ),
        log_dir=str(project_root / "logs" / "llm_provider"),
    )


def provider_from_environment(*, stage_name: str = "") -> LLMProviderConfig:
    return LLMProviderConfig(
        provider_mode=normalize_provider_mode(
            os.environ.get(f"{GENERAL_LLM_ENV_PREFIX}_MODE")
            or _dotenv_value(f"{GENERAL_LLM_ENV_PREFIX}_MODE")
            or "disabled"
        ),
        model=os.environ.get(f"{GENERAL_LLM_ENV_PREFIX}_MODEL") or _dotenv_value(f"{GENERAL_LLM_ENV_PREFIX}_MODEL"),
        api_key=os.environ.get(f"{GENERAL_LLM_ENV_PREFIX}_API_KEY") or _dotenv_value(f"{GENERAL_LLM_ENV_PREFIX}_API_KEY"),
        base_url=os.environ.get(f"{GENERAL_LLM_ENV_PREFIX}_BASE_URL") or _dotenv_value(f"{GENERAL_LLM_ENV_PREFIX}_BASE_URL"),
        command=os.environ.get(f"{GENERAL_LLM_ENV_PREFIX}_COMMAND") or _dotenv_value(f"{GENERAL_LLM_ENV_PREFIX}_COMMAND"),
        input_json_path=os.environ.get(f"{GENERAL_LLM_ENV_PREFIX}_INPUT_JSON") or _dotenv_value(f"{GENERAL_LLM_ENV_PREFIX}_INPUT_JSON"),
        timeout_seconds=_int_from_any(
            os.environ.get(f"{GENERAL_LLM_ENV_PREFIX}_TIMEOUT_SECONDS") or _dotenv_value(f"{GENERAL_LLM_ENV_PREFIX}_TIMEOUT_SECONDS"),
            120,
        ),
        max_tokens=_int_from_any(
            os.environ.get(f"{GENERAL_LLM_ENV_PREFIX}_MAX_TOKENS") or _dotenv_value(f"{GENERAL_LLM_ENV_PREFIX}_MAX_TOKENS"),
            7000,
        ),
        stage_name=stage_name,
        env_prefix=GENERAL_LLM_ENV_PREFIX,
        log_dir=None,
    )
