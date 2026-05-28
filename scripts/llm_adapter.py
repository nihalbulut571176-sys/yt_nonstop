from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Any

from project_pipeline_utils import load_json


@dataclass(frozen=True)
class PromptAuthoringRequest:
    project_json: Path
    scene_context_pack_path: Path
    visual_bible_path: Path
    llm_prompt_drafts_path: Path


class LLMArtifactAdapter(Protocol):
    def load_visual_bible(self, request: PromptAuthoringRequest) -> dict[str, Any]:
        ...

    def load_prompt_drafts(self, request: PromptAuthoringRequest) -> list[dict[str, Any]]:
        ...


class FileArtifactLLMAdapter:
    """Hybrid JSON adapter: LLM-authored artifacts are read from project files and validated by Python."""

    def load_visual_bible(self, request: PromptAuthoringRequest) -> dict[str, Any]:
        return load_json(request.visual_bible_path)

    def load_prompt_drafts(self, request: PromptAuthoringRequest) -> list[dict[str, Any]]:
        return load_json(request.llm_prompt_drafts_path)


class APIArtifactLLMAdapter:
    """Reserved transport interface for future automated LLM calls.

    This adapter intentionally does not write repo-tracked artifacts directly.
    Python remains responsible for persisting, validating, and merging any results.
    """

    def load_visual_bible(self, request: PromptAuthoringRequest) -> dict[str, Any]:
        raise NotImplementedError("API transport is not wired yet; use file-based artifacts for the current workflow")

    def load_prompt_drafts(self, request: PromptAuthoringRequest) -> list[dict[str, Any]]:
        raise NotImplementedError("API transport is not wired yet; use file-based artifacts for the current workflow")
