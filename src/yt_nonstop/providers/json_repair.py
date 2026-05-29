from __future__ import annotations

import json
import re
from typing import Any


def extract_json_payload(value: Any, *, allow_array: bool = False) -> Any:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        if allow_array:
            return value
        raise ValueError("Top-level JSON array is not allowed")
    text = str(value or "").strip()
    if not text:
        raise ValueError("Provider returned empty content")
    try:
        payload = json.loads(text)
        if isinstance(payload, list) and not allow_array:
            raise ValueError("Top-level JSON array is not allowed")
        return payload
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        candidate = fenced.group(1).strip()
        payload = json.loads(candidate)
        if isinstance(payload, list) and not allow_array:
            raise ValueError("Top-level JSON array is not allowed")
        return payload
    decoder = json.JSONDecoder()
    for match in re.finditer(r"[\{\[]", text):
        start = match.start()
        try:
            payload, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if text[start + end :].strip():
            # Explanatory tail is allowed.
            pass
        if isinstance(payload, list) and not allow_array:
            raise ValueError("Top-level JSON array is not allowed")
        return payload
    raise ValueError("No valid top-level JSON payload found")


def validate_json_object(payload: Any, *, required_keys: list[str] | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Response must be a JSON object")
    required = required_keys or []
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"Missing required keys: {', '.join(missing)}")
    return payload
