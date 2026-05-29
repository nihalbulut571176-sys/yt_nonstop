from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_json_only_prompt(*, instruction: str, context: dict[str, Any]) -> str:
    return f"{instruction}\nReturn JSON only.\n\n```json\n{json.dumps(context, ensure_ascii=False, indent=2)}\n```"


def build_repair_payload(
    *,
    task_name: str,
    schema_name: str | None,
    original_user_payload: dict[str, Any],
    invalid_response_text: str,
    validation_error: str,
    required_keys: list[str] | None,
) -> dict[str, Any]:
    return {
        "task_name": task_name,
        "schema_name": schema_name,
        "original_user_payload": original_user_payload,
        "invalid_response_text": invalid_response_text,
        "validation_error": validation_error,
        "required_keys": required_keys or [],
        "rules": [
            "Return JSON only.",
            "Preserve the original task meaning.",
            "Do not invent timing, file paths, job ids, runtime statuses, or saved file states.",
        ],
    }


def load_prompt_text(path: str | Path | None) -> str:
    if not path:
        return ""
    return Path(path).read_text(encoding="utf-8")
