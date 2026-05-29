"""External LLM provider boundary for visual allocation authoring.

This module intentionally avoids binding the pipeline to one vendor SDK.  The
visual allocation stage can be powered by:

- command: an executable that receives a JSON request on stdin and writes JSON
  to stdout; useful for Codex/CLI/internal agents.
- http: a generic JSON endpoint that receives the same request shape.
- openai_compatible: a Chat Completions compatible HTTP endpoint.

The provider only authors creative visual-slot decisions.  Python still owns
normalization, timing validation, file paths, locking, execution, and reports.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ALLOWED_EXTERNAL_MODES = {"command", "http", "openai_compatible"}
DEFAULT_OPENAI_COMPATIBLE_URL = "https://api.openai.com/v1/chat/completions"


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def load_text(path: Path, fallback: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return fallback


def extract_json_payload(value: Any) -> Any:
    """Parse JSON returned by an LLM, with fenced-code fallback."""
    if isinstance(value, (dict, list)):
        return value
    text = str(value or "").strip()
    if not text:
        raise RuntimeError("External visual allocation provider returned empty content")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass
    starts = [index for index in (text.find("{"), text.find("[")) if index >= 0]
    if not starts:
        raise RuntimeError("External visual allocation provider did not return JSON")
    start = min(starts)
    end_obj = text.rfind("}")
    end_arr = text.rfind("]")
    end = max(end_obj, end_arr)
    if end <= start:
        raise RuntimeError("External visual allocation provider returned malformed JSON")
    return json.loads(text[start : end + 1])


def visual_slots_from_payload(payload: Any) -> list[dict[str, Any]]:
    parsed = extract_json_payload(payload)
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        slots = parsed.get("visual_slots") or parsed.get("slots") or parsed.get("data")
        if isinstance(slots, list):
            return [item for item in slots if isinstance(item, dict)]
        # Some providers wrap text content in a JSON field.
        for key in ("content", "text", "message", "output"):
            if isinstance(parsed.get(key), str):
                return visual_slots_from_payload(parsed[key])
    raise RuntimeError("External visual allocation provider JSON has no visual_slots array")


@dataclass
class ExternalVisualAllocationConfig:
    mode: str
    command: str | list[str] | None = None
    endpoint_url: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None
    model: str | None = None
    temperature: float = 0.2
    max_tokens: int = 7000
    timeout_seconds: float = 120.0
    system_prompt_path: str | None = None
    user_prompt_template_path: str | None = None

    @property
    def resolved_api_key(self) -> str | None:
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            return os.environ.get(self.api_key_env)
        return os.environ.get("YT_NONSTOP_VISUAL_ALLOCATOR_API_KEY") or os.environ.get("OPENAI_API_KEY")


def _float_from_any(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_from_any(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def config_from_project(project: dict[str, Any]) -> ExternalVisualAllocationConfig:
    raw = dict(project.get("planning", {}).get("visual_allocation_llm", {}) or {})
    mode = clean_text(
        os.environ.get("YT_NONSTOP_VISUAL_ALLOCATOR_MODE")
        or raw.get("mode")
        or raw.get("provider")
        or ""
    ).lower()
    if not mode:
        if os.environ.get("YT_NONSTOP_VISUAL_ALLOCATOR_CMD") or raw.get("command"):
            mode = "command"
        elif os.environ.get("YT_NONSTOP_VISUAL_ALLOCATOR_URL") or raw.get("endpoint_url"):
            mode = "http"
        else:
            mode = "openai_compatible"
    if mode in {"openai", "openai_chat", "chat_completions"}:
        mode = "openai_compatible"
    if mode not in ALLOWED_EXTERNAL_MODES:
        raise RuntimeError(f"Unsupported visual allocation external provider mode `{mode}`")
    return ExternalVisualAllocationConfig(
        mode=mode,
        command=os.environ.get("YT_NONSTOP_VISUAL_ALLOCATOR_CMD") or raw.get("command"),
        endpoint_url=os.environ.get("YT_NONSTOP_VISUAL_ALLOCATOR_URL") or raw.get("endpoint_url"),
        api_key=os.environ.get("YT_NONSTOP_VISUAL_ALLOCATOR_API_KEY") or raw.get("api_key"),
        api_key_env=os.environ.get("YT_NONSTOP_VISUAL_ALLOCATOR_API_KEY_ENV") or raw.get("api_key_env"),
        model=os.environ.get("YT_NONSTOP_VISUAL_ALLOCATOR_MODEL") or raw.get("model") or "gpt-4.1-mini",
        temperature=_float_from_any(os.environ.get("YT_NONSTOP_VISUAL_ALLOCATOR_TEMPERATURE") or raw.get("temperature"), 0.2),
        max_tokens=_int_from_any(os.environ.get("YT_NONSTOP_VISUAL_ALLOCATOR_MAX_TOKENS") or raw.get("max_tokens"), 7000),
        timeout_seconds=_float_from_any(os.environ.get("YT_NONSTOP_VISUAL_ALLOCATOR_TIMEOUT_SECONDS") or raw.get("timeout_seconds"), 120.0),
        system_prompt_path=os.environ.get("YT_NONSTOP_VISUAL_ALLOCATOR_SYSTEM_PROMPT") or raw.get("system_prompt_path"),
        user_prompt_template_path=os.environ.get("YT_NONSTOP_VISUAL_ALLOCATOR_USER_TEMPLATE") or raw.get("user_prompt_template_path"),
    )


def _compact_scene(scene: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "scene_id",
        "global_scene_id",
        "start",
        "end",
        "duration",
        "voice_text",
        "visual_goal",
        "visualized_claim",
        "must_show",
        "film_block_id",
        "environment",
        "camera",
        "lighting",
        "lighting_family",
        "active_entity_ids",
        "continuity_cast",
    ]
    return {key: scene.get(key) for key in keys if scene.get(key) not in (None, "", [])}


def _compact_beat(beat: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "beat_id",
        "scene_id",
        "start",
        "end",
        "duration",
        "voice_text",
        "spoken_claim",
        "must_visualize",
        "entity_mentions",
        "location_mentions",
        "beat_role",
        "visual_priority",
    ]
    return {key: beat.get(key) for key in keys if beat.get(key) not in (None, "", [])}


def build_visual_allocation_context(
    *,
    beats: list[dict[str, Any]],
    scene_plan: dict[str, Any],
    project: dict[str, Any],
    policy: dict[str, Any],
    allowed_generation_decisions: list[str],
    allowed_slot_types: list[str],
    previous_errors: list[str] | None = None,
    previous_warnings: list[str] | None = None,
    previous_slots: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    generation = project.get("generation", {}) or {}
    prompts = project.get("prompts", {}) or {}
    visual_bible = {}
    visual_bible_path = prompts.get("visual_bible_path")
    if visual_bible_path:
        try:
            visual_bible = json.loads(Path(visual_bible_path).read_text(encoding="utf-8-sig"))
        except Exception:
            visual_bible = {}
    return {
        "task": "author_visual_allocation_plan",
        "project_id": project.get("project_id"),
        "profile_id": project.get("profile_id"),
        "language": project.get("meta", {}).get("language"),
        "workflow": {
            "is_sequence": project.get("workflow", {}).get("is_sequence", True),
            "requested_format": project.get("workflow", {}).get("requested_format"),
        },
        "policy": policy,
        "variant_policy": {
            "normal_beat_variants": int(generation.get("normal_beat_variants", 1) or 1),
            "key_beat_variants": int(generation.get("key_beat_variants", 3) or 3),
            "max_variants_per_slot": int(generation.get("max_variants_per_slot", 4) or 4),
        },
        "allowed_generation_decisions": allowed_generation_decisions,
        "allowed_slot_types": allowed_slot_types,
        "visual_bible": visual_bible,
        "narration_beats": [_compact_beat(beat) for beat in beats],
        "scenes": [_compact_scene(scene) for scene in scene_plan.get("scenes", [])],
        "requirements": [
            "Return JSON only with a top-level visual_slots array.",
            "Use exact timing from narration beats; do not invent audio time outside SRT bounds.",
            "Decide the number of visual slots as a director: one beat may become multiple slots, and a slot may cover multiple beats only when visually justified.",
            "Every new visual slot must add new visual information; do not use reuse/hold to save cost.",
            "Each must_show item must be concrete, visible, drawable, and not abstract.",
            "Do not put file paths, API job ids, image paths, statuses, or runtime state in the JSON.",
            "Use hold_previous or continuation_motion only when it improves pacing and the previous image still visualizes the current narration.",
        ],
        "repair_context": {
            "previous_errors": previous_errors or [],
            "previous_warnings": previous_warnings or [],
            "previous_slots": previous_slots or [],
        } if previous_errors or previous_warnings else None,
    }


def render_user_prompt(context: dict[str, Any]) -> str:
    return (
        "Author a visual_allocation_plan.json for this narrated video.\n"
        "Use the JSON context below. Return JSON only.\n\n"
        f"```json\n{json.dumps(context, ensure_ascii=False, indent=2)}\n```"
    )


class ExternalVisualAllocationLLMProvider:
    provider_name = "external_visual_allocation_llm_v1"

    def __init__(self, project: dict[str, Any], repo_root: Path | None = None) -> None:
        self.project = project
        self.repo_root = repo_root or Path(__file__).resolve().parents[1]
        self.config = config_from_project(project)

    def system_prompt(self) -> str:
        default_path = self.repo_root / "prompts" / "visual_allocation_system_prompt.md"
        path = Path(self.config.system_prompt_path) if self.config.system_prompt_path else default_path
        return load_text(path, fallback="You are a visual director. Return valid JSON only.")

    def user_template(self) -> str:
        default_path = self.repo_root / "prompts" / "visual_allocation_user_template.md"
        path = Path(self.config.user_prompt_template_path) if self.config.user_prompt_template_path else default_path
        return load_text(path, fallback="{context_json}")

    def call(self, request_payload: dict[str, Any]) -> Any:
        mode = self.config.mode
        if mode == "command":
            return self._call_command(request_payload)
        if mode == "http":
            return self._call_http(request_payload)
        if mode == "openai_compatible":
            return self._call_openai_compatible(request_payload)
        raise RuntimeError(f"Unsupported external visual allocation mode `{mode}`")

    def author_visual_slots(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        system_prompt = self.system_prompt()
        context_json = json.dumps(context, ensure_ascii=False, indent=2)
        template = self.user_template()
        user_prompt = template.replace("{context_json}", context_json)
        request_payload = {
            "task": "author_visual_allocation_plan",
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "context": context,
            "response_contract": {
                "format": "json",
                "top_level_key": "visual_slots",
            },
        }
        return visual_slots_from_payload(self.call(request_payload))

    def _call_command(self, request_payload: dict[str, Any]) -> Any:
        command = self.config.command
        if not command:
            raise RuntimeError("command mode requires YT_NONSTOP_VISUAL_ALLOCATOR_CMD or planning.visual_allocation_llm.command")
        argv = command if isinstance(command, list) else shlex.split(str(command))
        if not argv:
            raise RuntimeError("visual allocation command provider command is empty")
        completed = subprocess.run(
            argv,
            input=json.dumps(request_payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=self.config.timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "visual allocation command provider failed "
                f"with exit code {completed.returncode}: {completed.stderr.strip()}"
            )
        return extract_json_payload(completed.stdout)

    def _call_http(self, request_payload: dict[str, Any]) -> Any:
        url = self.config.endpoint_url
        if not url:
            raise RuntimeError("http mode requires YT_NONSTOP_VISUAL_ALLOCATOR_URL or planning.visual_allocation_llm.endpoint_url")
        return self._post_json(url, request_payload)

    def _call_openai_compatible(self, request_payload: dict[str, Any]) -> Any:
        api_key = self.config.resolved_api_key
        if not api_key:
            raise RuntimeError(
                "openai_compatible mode requires an API key via OPENAI_API_KEY, "
                "YT_NONSTOP_VISUAL_ALLOCATOR_API_KEY, or planning.visual_allocation_llm.api_key_env"
            )
        url = self.config.endpoint_url or DEFAULT_OPENAI_COMPATIBLE_URL
        body = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "messages": [
                {"role": "system", "content": request_payload["system_prompt"]},
                {"role": "user", "content": request_payload["user_prompt"]},
            ],
            "response_format": {"type": "json_object"},
        }
        response = self._post_json(url, body, bearer_token=api_key)
        if isinstance(response, dict):
            choices = response.get("choices") or []
            if choices:
                message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
                content = message.get("content")
                if content:
                    return extract_json_payload(content)
            # Some compatible endpoints return direct output fields.
            for key in ("output_text", "content", "text"):
                if response.get(key):
                    return extract_json_payload(response[key])
        return response

    def _post_json(self, url: str, payload: dict[str, Any], bearer_token: str | None = None) -> Any:
        headers = {"Content-Type": "application/json"}
        api_key = bearer_token or self.config.resolved_api_key
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"visual allocation HTTP provider failed {exc.code}: {body}") from exc
        return extract_json_payload(text)
