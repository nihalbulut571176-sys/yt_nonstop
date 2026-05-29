import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

from yt_nonstop.providers.llm_provider import (
    LLMJSONValidationError,
    LLMProviderConfig,
    LLMProviderNotConfiguredError,
    LLMProviderResponseError,
    _normalize_openai_url,
    complete_json,
    extract_json_payload,
)
from yt_nonstop.providers.provider_config import provider_from_environment, provider_from_project


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_extract_json_payload_handles_pure_json() -> None:
    assert extract_json_payload('{"ok": true}') == {"ok": True}


def test_extract_json_payload_handles_fenced_json() -> None:
    assert extract_json_payload('```json\n{"ok": true}\n```') == {"ok": True}


def test_extract_json_payload_handles_text_before_and_after_json() -> None:
    assert extract_json_payload('Answer follows:\n{"ok": true}\nThanks.') == {"ok": True}


def test_extract_json_payload_raises_on_invalid_json() -> None:
    with pytest.raises(ValueError):
        extract_json_payload("not json at all")


def test_extract_json_payload_rejects_top_level_array() -> None:
    with pytest.raises(ValueError, match="Top-level JSON array"):
        extract_json_payload('[{"ok": true}]')


def test_normalize_openai_url_maps_fastgen_site_to_googler_endpoint() -> None:
    assert _normalize_openai_url("https://fast-gen.ai/v1") == "https://googler.fast-gen.ai/v1/chat/completions"


def test_file_provider_reads_json_and_validates_required_keys() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        input_path = Path(tmp) / "input.json"
        write_json(input_path, {"ok": True, "value": 1})
        config = LLMProviderConfig(provider_mode="file", input_json_path=str(input_path))
        payload = complete_json(
            "file_provider_test",
            "Return JSON only.",
            {"request": "demo"},
            schema_name="file_schema.v1",
            required_keys=["ok"],
            provider_config=config,
        )
        assert payload["ok"] is True


def test_command_provider_receives_stdin_json_and_returns_object() -> None:
    script = (
        "import json,sys;"
        "req=json.load(sys.stdin);"
        "sys.stdout.write(json.dumps({'task': req['task_name'], 'ok': True}))"
    )
    config = LLMProviderConfig(provider_mode="command", command=[sys.executable, "-c", script], timeout_seconds=5)
    payload = complete_json(
        "command_provider_test",
        "Return JSON only.",
        {"request": "demo"},
        schema_name="command_schema.v1",
        required_keys=["task", "ok"],
        provider_config=config,
    )
    assert payload == {"task": "command_provider_test", "ok": True}


def test_command_provider_nonzero_exit_raises_clear_error() -> None:
    script = "import sys; sys.stderr.write('boom'); raise SystemExit(7)"
    config = LLMProviderConfig(provider_mode="command", command=[sys.executable, "-c", script], timeout_seconds=5)
    with pytest.raises(LLMProviderResponseError, match=r"nonzero_test: .*code 7"):
        complete_json("nonzero_test", "Return JSON only.", {"request": "demo"}, provider_config=config)


def test_command_provider_timeout_raises_clear_error() -> None:
    script = "import time; time.sleep(2); print('{\"ok\": true}')"
    config = LLMProviderConfig(provider_mode="command", command=[sys.executable, "-c", script], timeout_seconds=1)
    with pytest.raises(LLMProviderResponseError, match=r"timeout_test: .*timed out"):
        complete_json("timeout_test", "Return JSON only.", {"request": "demo"}, provider_config=config)


def test_disabled_provider_fails_fast() -> None:
    with pytest.raises(LLMProviderNotConfiguredError, match=r"disabled_test: .*disabled"):
        complete_json(
            "disabled_test",
            "Return JSON only.",
            {"request": "demo"},
            provider_config=LLMProviderConfig(provider_mode="disabled"),
        )


def test_repair_loop_recovers_after_invalid_first_response(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        counter_path = Path(tmp) / "counter.txt"
        script = (
            "import json, os, pathlib, sys;"
            "counter = pathlib.Path(os.environ['YT_TEST_COUNTER']);"
            "count = int(counter.read_text() or '0') if counter.exists() else 0;"
            "counter.write_text(str(count + 1));"
            "sys.stdout.write('not-json' if count == 0 else json.dumps({'ok': True, 'fixed': True}))"
        )
        monkeypatch.setenv("YT_TEST_COUNTER", str(counter_path))
        config = LLMProviderConfig(provider_mode="command", command=[sys.executable, "-c", script], timeout_seconds=5)
        payload = complete_json(
            "repair_test",
            "Return JSON only.",
            {"request": "demo"},
            schema_name="repair_schema.v1",
            required_keys=["ok", "fixed"],
            max_repair_attempts=1,
            provider_config=config,
        )
        assert payload == {"ok": True, "fixed": True}


def test_repair_loop_raises_after_exhaustion() -> None:
    script = "import sys; sys.stdout.write('still not json')"
    config = LLMProviderConfig(provider_mode="command", command=[sys.executable, "-c", script], timeout_seconds=5)
    with pytest.raises(LLMJSONValidationError, match="repair_fail_test \\[repair_schema.v1\\]"):
        complete_json(
            "repair_fail_test",
            "Return JSON only.",
            {"request": "demo"},
            schema_name="repair_schema.v1",
            required_keys=["ok"],
            max_repair_attempts=1,
            provider_config=config,
        )


def test_provider_from_project_reads_llm_defaults_from_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        dotenv_path = tmp_path / ".env"
        dotenv_path.write_text(
            "\n".join(
                [
                    "YT_NONSTOP_LLM_PROVIDER_MODE=openai_compatible",
                    "YT_NONSTOP_LLM_PROVIDER_API_KEY=fastgen-test-key",
                    "YT_NONSTOP_LLM_PROVIDER_BASE_URL=https://fast-gen.ai/v1",
                    "YT_NONSTOP_LLM_PROVIDER_MODEL=openai/gpt-4o",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("yt_nonstop.providers.provider_config.ENV_PATH", dotenv_path)
        monkeypatch.delenv("YT_NONSTOP_LLM_PROVIDER_MODE", raising=False)
        monkeypatch.delenv("YT_NONSTOP_LLM_PROVIDER_API_KEY", raising=False)
        monkeypatch.delenv("YT_NONSTOP_LLM_PROVIDER_BASE_URL", raising=False)
        monkeypatch.delenv("YT_NONSTOP_LLM_PROVIDER_MODEL", raising=False)

        project = {
            "meta": {"project_root": str(tmp_path / "project")},
            "providers": {"llm_provider": {}},
            "prompts": {"prompt_authoring_llm": {"mode": "openai_compatible"}},
        }

        config = provider_from_project(project, stage_name="auto_author_llm_prompts")
        assert config.mode == "openai_compatible"
        assert config.api_key == "fastgen-test-key"
        assert config.base_url == "https://fast-gen.ai/v1"
        assert config.model == "openai/gpt-4o"


def test_provider_from_environment_reads_dotenv_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        dotenv_path = tmp_path / ".env"
        dotenv_path.write_text(
            "YT_NONSTOP_LLM_PROVIDER_MODE=openai_compatible\n"
            "YT_NONSTOP_LLM_PROVIDER_API_KEY=fastgen-test-key\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("yt_nonstop.providers.provider_config.ENV_PATH", dotenv_path)
        monkeypatch.delenv("YT_NONSTOP_LLM_PROVIDER_MODE", raising=False)
        monkeypatch.delenv("YT_NONSTOP_LLM_PROVIDER_API_KEY", raising=False)

        config = provider_from_environment(stage_name="auto_author_llm_prompts")
        assert config.mode == "openai_compatible"
        assert config.api_key == "fastgen-test-key"
