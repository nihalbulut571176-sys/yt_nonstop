"""Unified LLM provider boundary for authored JSON artifacts."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yt_nonstop.providers.json_repair import extract_json_payload, validate_json_object
from yt_nonstop.providers.prompt_loader import build_json_only_prompt, build_repair_payload
from yt_nonstop.providers.provider_config import (
    ALLOWED_LLM_PROVIDER_MODES,
    DEFAULT_STAGE_CONFIG,
    GENERAL_LLM_ENV_PREFIX,
    LLMProviderConfig,
    normalize_provider_mode,
    provider_from_environment,
    provider_from_project,
)
from yt_nonstop.utils.json_io import save_json


DEFAULT_OPENAI_COMPATIBLE_URL = "https://api.openai.com/v1/chat/completions"
FAST_GEN_OPENAI_COMPATIBLE_URL = "https://googler.fast-gen.ai/v1/chat/completions"


class LLMProviderError(Exception):
    pass


class LLMProviderNotConfiguredError(LLMProviderError):
    pass


class LLMProviderResponseError(LLMProviderError):
    pass


class LLMJSONValidationError(LLMProviderError):
    pass


def _format_error(task_name: str, schema_name: str | None, message: str) -> str:
    if schema_name:
        return f"{task_name} [{schema_name}]: {message}"
    return f"{task_name}: {message}"


def _normalize_openai_url(base_url: str | None) -> str:
    if not base_url:
        return DEFAULT_OPENAI_COMPATIBLE_URL
    url = str(base_url).rstrip("/")
    if url in {"https://fast-gen.ai", "https://fast-gen.ai/v1"}:
        return FAST_GEN_OPENAI_COMPATIBLE_URL
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return f"{url}/chat/completions"
    return f"{url}/v1/chat/completions"


def _coerce_assistant_content(message_content: Any) -> str:
    if isinstance(message_content, str):
        return message_content
    if isinstance(message_content, list):
        parts: list[str] = []
        for item in message_content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    return str(message_content or "")


@dataclass
class LLMRequest:
    stage_name: str
    task: str
    contract_name: str
    system_prompt: str
    user_prompt: str
    context: dict[str, Any]
    response_key: str | None = None


@dataclass
class LLMResponse:
    provider_name: str
    mode: str
    payload: Any
    raw_text: str
    request_log_path: str | None = None
    response_log_path: str | None = None


class LLMProvider:
    provider_name = "unified_llm_provider_v2"

    def __init__(self, config: LLMProviderConfig) -> None:
        self.config = config

    def _log(self, suffix: str, payload: Any) -> str | None:
        if not self.config.log_dir:
            return None
        log_dir = Path(self.config.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"{self.config.stage_name or 'llm'}_{suffix}.json"
        save_json(path, payload)
        return str(path)

    def _request_payload(
        self,
        *,
        task_name: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        schema_name: str | None,
        required_keys: list[str] | None,
    ) -> dict[str, Any]:
        return {
            "task_name": task_name,
            "schema_name": schema_name,
            "system_prompt": system_prompt,
            "user_payload": user_payload,
            "required_keys": required_keys or [],
            "response_format": "json_object",
        }

    def _invoke_raw(
        self,
        *,
        task_name: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        schema_name: str | None,
        required_keys: list[str] | None,
    ) -> tuple[str, str | None, str | None]:
        request_payload = self._request_payload(
            task_name=task_name,
            system_prompt=system_prompt,
            user_payload=user_payload,
            schema_name=schema_name,
            required_keys=required_keys,
        )
        request_log_path = self._log("request", request_payload)
        mode = self.config.provider_mode
        if mode == "disabled":
            raise LLMProviderNotConfiguredError(_format_error(task_name, schema_name, "LLM provider is disabled"))
        if mode == "file":
            if not self.config.input_json_path:
                raise LLMProviderNotConfiguredError(_format_error(task_name, schema_name, "file provider requires input_json_path"))
            raw_text = Path(self.config.input_json_path).read_text(encoding="utf-8")
        elif mode == "command":
            raw_text = self._call_command(request_payload, task_name=task_name, schema_name=schema_name)
        elif mode == "http":
            raw_text = self._call_http(request_payload, task_name=task_name, schema_name=schema_name)
        elif mode == "openai_compatible":
            raw_text = self._call_openai_compatible(request_payload, task_name=task_name, schema_name=schema_name)
        else:  # pragma: no cover
            raise LLMProviderNotConfiguredError(_format_error(task_name, schema_name, f"Unsupported LLM provider mode `{mode}`"))
        response_log_path = self._log("response", {"task_name": task_name, "schema_name": schema_name, "raw_text": raw_text})
        return raw_text, request_log_path, response_log_path

    def _call_command(self, request_payload: dict[str, Any], *, task_name: str, schema_name: str | None) -> str:
        command = self.config.command
        if not command:
            raise LLMProviderNotConfiguredError(_format_error(task_name, schema_name, "command provider requires command"))
        try:
            completed = subprocess.run(
                command,
                input=json.dumps(request_payload, ensure_ascii=False),
                text=True,
                capture_output=True,
                timeout=self.config.timeout_seconds,
                check=False,
                shell=isinstance(command, str),
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMProviderResponseError(_format_error(task_name, schema_name, f"command provider timed out after {self.config.timeout_seconds}s")) from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise LLMProviderResponseError(_format_error(task_name, schema_name, f"command provider exited with code {completed.returncode}: {detail}"))
        return completed.stdout

    def _call_http(self, request_payload: dict[str, Any], *, task_name: str, schema_name: str | None) -> str:
        if not self.config.base_url:
            raise LLMProviderNotConfiguredError(_format_error(task_name, schema_name, "http provider requires base_url"))
        body = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        request = urllib.request.Request(self.config.base_url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:  # pragma: no cover
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMProviderResponseError(_format_error(task_name, schema_name, f"http provider returned {exc.code}: {detail}")) from exc
        except urllib.error.URLError as exc:  # pragma: no cover
            raise LLMProviderResponseError(_format_error(task_name, schema_name, f"http provider failed: {exc.reason}")) from exc

    def _call_openai_compatible(self, request_payload: dict[str, Any], *, task_name: str, schema_name: str | None) -> str:
        if not self.config.api_key:
            raise LLMProviderNotConfiguredError(_format_error(task_name, schema_name, "openai_compatible provider requires api_key"))
        body = {
            "model": self.config.model or "gpt-4.1-mini",
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "messages": [
                {"role": "system", "content": request_payload["system_prompt"]},
                {"role": "user", "content": json.dumps(request_payload["user_payload"], ensure_ascii=False, indent=2)},
            ],
            "response_format": {"type": "json_object"},
        }
        url = _normalize_openai_url(self.config.base_url)
        raw_text = self._call_http_like_openai(url, body, api_key=self.config.api_key, task_name=task_name, schema_name=schema_name)
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise LLMProviderResponseError(_format_error(task_name, schema_name, "openai_compatible provider returned non-JSON response")) from exc
        if isinstance(payload, dict):
            choices = payload.get("choices") or []
            if choices and isinstance(choices[0], dict):
                message = choices[0].get("message", {})
                return _coerce_assistant_content(message.get("content"))
        raise LLMProviderResponseError(_format_error(task_name, schema_name, "openai_compatible provider returned no assistant message content"))

    def _call_http_like_openai(self, url: str, payload: dict[str, Any], *, api_key: str, task_name: str, schema_name: str | None) -> str:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:  # pragma: no cover
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMProviderResponseError(_format_error(task_name, schema_name, f"openai_compatible provider returned {exc.code}: {detail}")) from exc
        except urllib.error.URLError as exc:  # pragma: no cover
            raise LLMProviderResponseError(_format_error(task_name, schema_name, f"openai_compatible provider failed: {exc.reason}")) from exc

    def invoke(self, request: LLMRequest) -> LLMResponse:
        raw_text, request_log_path, response_log_path = self._invoke_raw(
            task_name=request.task,
            system_prompt=request.system_prompt,
            user_payload={"user_prompt": request.user_prompt, "context": request.context},
            schema_name=request.contract_name,
            required_keys=[request.response_key] if request.response_key else None,
        )
        payload = extract_json_payload(raw_text, allow_array=bool(request.response_key))
        if request.response_key and isinstance(payload, list):
            payload = {request.response_key: payload}
        return LLMResponse(
            provider_name=f"{self.provider_name}:{self.config.provider_mode}",
            mode=self.config.provider_mode,
            payload=payload,
            raw_text=raw_text,
            request_log_path=request_log_path,
            response_log_path=response_log_path,
        )

    def complete_json(
        self,
        task_name: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        *,
        schema_name: str | None = None,
        required_keys: list[str] | None = None,
        max_repair_attempts: int = 1,
    ) -> dict[str, Any]:
        last_error: str | None = None
        invalid_response_text = ""
        current_system_prompt = system_prompt
        current_user_payload = user_payload
        for attempt in range(max_repair_attempts + 1):
            raw_text, _, _ = self._invoke_raw(
                task_name=task_name,
                system_prompt=current_system_prompt,
                user_payload=current_user_payload,
                schema_name=schema_name,
                required_keys=required_keys,
            )
            invalid_response_text = raw_text
            try:
                payload = extract_json_payload(raw_text, allow_array=False)
                return validate_json_object(payload, required_keys=required_keys)
            except (ValueError, json.JSONDecodeError) as exc:
                last_error = str(exc)
                if attempt >= max_repair_attempts or self.config.provider_mode == "file":
                    break
                current_system_prompt = "You repair invalid machine-readable JSON. Return JSON only."
                current_user_payload = build_repair_payload(
                    task_name=task_name,
                    schema_name=schema_name,
                    original_user_payload=user_payload,
                    invalid_response_text=invalid_response_text,
                    validation_error=last_error,
                    required_keys=required_keys,
                )
        raise LLMJSONValidationError(_format_error(task_name, schema_name, last_error or "invalid JSON response"))


def complete_json(
    task_name: str,
    system_prompt: str,
    user_payload: dict[str, Any],
    *,
    schema_name: str | None = None,
    required_keys: list[str] | None = None,
    max_repair_attempts: int = 1,
    provider_config: LLMProviderConfig | None = None,
) -> dict[str, Any]:
    config = provider_config or provider_from_environment(stage_name=task_name)
    provider = LLMProvider(config)
    return provider.complete_json(
        task_name,
        system_prompt,
        user_payload,
        schema_name=schema_name,
        required_keys=required_keys,
        max_repair_attempts=max_repair_attempts,
    )


__all__ = [
    "ALLOWED_LLM_PROVIDER_MODES",
    "DEFAULT_STAGE_CONFIG",
    "GENERAL_LLM_ENV_PREFIX",
    "LLMJSONValidationError",
    "LLMProvider",
    "LLMProviderConfig",
    "LLMProviderError",
    "LLMProviderNotConfiguredError",
    "LLMProviderResponseError",
    "LLMRequest",
    "LLMResponse",
    "build_json_only_prompt",
    "complete_json",
    "extract_json_payload",
    "normalize_provider_mode",
    "provider_from_environment",
    "provider_from_project",
]
