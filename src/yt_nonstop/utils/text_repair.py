from __future__ import annotations

from typing import Any


MOJIBAKE_MARKERS = (
    "РџС",
    "РљР",
    "СЃ",
    "С‚",
    "Рё",
    "Р°",
    "В«",
    "В»",
    "вЂ”",
    "вЂ¦",
)


def looks_like_mojibake(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    if any(marker in value for marker in MOJIBAKE_MARKERS):
        return True
    cyrillic_like = value.count("Р") + value.count("С") + value.count("Ѓ") + value.count("Ђ")
    return cyrillic_like >= 4 and " " in value


def repair_mojibake_text(text: str) -> str:
    value = str(text or "")
    if not looks_like_mojibake(value):
        return value
    for source_encoding in ("cp1251", "latin1"):
        try:
            repaired = value.encode(source_encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if repaired and repaired != value:
            return repaired
    return value


def repair_payload_strings(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {key: repair_payload_strings(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [repair_payload_strings(item) for item in payload]
    if isinstance(payload, str):
        return repair_mojibake_text(payload)
    return payload
