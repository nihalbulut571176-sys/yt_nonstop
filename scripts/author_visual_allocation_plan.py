import argparse
import os
from pathlib import Path
from typing import Any, Protocol

from project_pipeline_utils import load_json, load_project, save_json, save_project
from prompt_safety import is_probably_abstract, lint_prompt_observability
from llm_visual_allocation_provider import build_visual_allocation_context
from yt_nonstop.providers.llm_provider import build_json_only_prompt, complete_json, provider_from_project as provider_config_from_project


ALLOWED_GENERATION_DECISIONS = {
    "new_image",
    "new_angle_same_setup",
    "detail_insert",
    "reaction_shot",
    "establishing_shot",
    "hold_previous",
    "continuation_motion",
    "manual_asset",
}

ALLOWED_SLOT_TYPES = {
    "establishing_shot",
    "character_action",
    "detail_insert",
    "reaction_shot",
    "context_detail",
    "evidence_insert",
    "explanation_visual",
    "atmosphere",
    "continuation_motion",
    "manual_asset",
}

ABSTRACT_ONLY_TERMS = {
    "betrayal",
    "danger",
    "truth",
    "corruption",
    "systemic failure",
    "reality",
    "logic",
    "identity",
    "network",
    "pressure",
    "fear",
    "mystery",
}


class VisualAllocationAdapter(Protocol):
    provider_name: str

    def author_visual_slots(
        self,
        beats: list[dict[str, Any]],
        scene_plan: dict[str, Any],
        project: dict[str, Any],
    ) -> list[dict[str, Any]]:
        ...


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def normalize_provider(value: Any) -> str:
    text = clean_text(value).lower().replace("-", "_")
    aliases = {
        "none": "disabled",
        "local": "disabled",
        "heuristic": "disabled",
        "llm": "external",
        "openai": "external",
    }
    return aliases.get(text, text or "disabled")


def provider_from_project(project: dict[str, Any], override: str | None = None, has_input_json: bool = False) -> str:
    if has_input_json:
        return "file"
    if override:
        normalized = normalize_provider(override)
        if normalized == "external":
            return provider_config_from_project(
                project,
                stage_name="author_visual_allocation_plan",
                override_mode="external",
            ).mode
        return normalized
    env_value = os.environ.get("YT_NONSTOP_VISUAL_ALLOCATION_PROVIDER")
    if env_value:
        normalized = normalize_provider(env_value)
        if normalized == "external":
            return provider_config_from_project(
                project,
                stage_name="author_visual_allocation_plan",
                override_mode="external",
            ).mode
        return normalized
    planning = project.get("planning", {})
    prompts = project.get("prompts", {})
    normalized = normalize_provider(
        planning.get("visual_allocation_provider")
        or prompts.get("visual_allocation_provider")
        or "disabled"
    )
    if normalized == "external":
        return provider_config_from_project(
            project,
            stage_name="author_visual_allocation_plan",
            override_mode="external",
        ).mode
    return normalized


def policy_from_project(project: dict[str, Any]) -> dict[str, float]:
    raw = project.get("planning", {}).get("visual_cadence_policy", {}) or {}
    return {
        "min_slot_duration_sec": float(raw.get("min_slot_duration_sec", 1.2) or 1.2),
        "target_slot_duration_sec": float(raw.get("target_slot_duration_sec", 3.2) or 3.2),
        "max_slot_duration_sec": float(raw.get("max_slot_duration_sec", 5.5) or 5.5),
        "max_static_hold_sec": float(raw.get("max_static_hold_sec", 6.5) or 6.5),
    }


def is_drawable_phrase(value: Any) -> bool:
    cleaned = clean_text(value)
    if not cleaned:
        return False
    lowered = cleaned.lower()
    if lowered in ABSTRACT_ONLY_TERMS or is_probably_abstract(cleaned):
        return False
    warnings = lint_prompt_observability(cleaned, what_is_in_frame=cleaned)
    return len(warnings) < 3


def drawable_items(values: list[Any], fallback: str) -> list[str]:
    result: list[str] = []
    seen = set()
    for value in values:
        cleaned = clean_text(value)
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        if is_drawable_phrase(cleaned):
            result.append(cleaned)
            seen.add(lowered)
    if not result and fallback:
        result = [fallback]
    return result[:4]


def slot_type_for(beat: dict[str, Any], item_index: int, total_items: int, beat_index: int) -> str:
    role = clean_text(beat.get("beat_role")).lower()
    if beat_index == 1 and item_index == 0:
        return "establishing_shot"
    if item_index > 0:
        if any(marker in role for marker in ("evidence", "reveal", "access", "theft", "document")):
            return "evidence_insert"
        return "detail_insert" if total_items >= 2 else "context_detail"
    if any(marker in role for marker in ("entry", "action", "assault", "access", "theft")):
        return "character_action"
    if any(marker in role for marker in ("evidence", "reveal", "document")):
        return "evidence_insert"
    if any(marker in role for marker in ("emotion", "reaction", "aftermath")):
        return "reaction_shot"
    return "explanation_visual"


def decision_for_slot(slot_type: str, item_index: int) -> str:
    if slot_type in {"establishing_shot", "detail_insert", "reaction_shot", "evidence_insert"}:
        return slot_type
    if item_index > 0:
        return "new_angle_same_setup"
    return "new_image"


def priority_for_slot(beat: dict[str, Any], slot_index: int) -> str:
    priority = clean_text(beat.get("visual_priority") or "low").lower()
    if priority not in {"high", "medium", "low"}:
        priority = "low"
    if slot_index == 0 and priority == "high":
        return "high"
    if priority == "high" and slot_index > 0:
        return "medium"
    return priority


def variants_for(priority: str, decision: str, project: dict[str, Any]) -> int:
    generation = project.get("generation", {})
    if decision in {"hold_previous", "continuation_motion"}:
        return 0
    if priority == "high":
        return int(generation.get("key_beat_variants", 3) or 3)
    return int(generation.get("normal_beat_variants", 1) or 1)


def split_windows(start: float, end: float, count: int) -> list[tuple[float, float]]:
    duration = max(0.0, end - start)
    if count <= 1 or duration <= 0:
        return [(round(start, 3), round(end, 3))]
    step = duration / count
    windows = []
    cursor = start
    for index in range(count):
        next_end = end if index == count - 1 else start + step * (index + 1)
        windows.append((round(cursor, 3), round(next_end, 3)))
        cursor = next_end
    return windows


class HeuristicVisualAllocationAdapter:
    """No-LLM bootstrap planner.

    This is intentionally conservative. It prefers new, purposeful visual slots
    over artificial reuse. Reuse/hold decisions are left for authored/file or
    external LLM plans unless the project explicitly supplies them.
    """

    provider_name = "heuristic_visual_allocation_v1"

    def author_visual_slots(
        self,
        beats: list[dict[str, Any]],
        scene_plan: dict[str, Any],
        project: dict[str, Any],
    ) -> list[dict[str, Any]]:
        policy = policy_from_project(project)
        scene_by_id = {scene.get("scene_id"): scene for scene in scene_plan.get("scenes", []) if scene.get("scene_id")}
        slots: list[dict[str, Any]] = []
        for beat_index, beat in enumerate(beats, start=1):
            scene = scene_by_id.get(beat.get("scene_id"), {})
            start = float(beat.get("start", scene.get("start", 0)) or 0)
            end = float(beat.get("end", scene.get("end", start)) or start)
            duration = max(0.001, end - start)
            must_items = drawable_items(
                list(beat.get("must_visualize", []) or scene.get("must_show", []) or []),
                clean_text(scene.get("visual_goal") or scene.get("voice_text") or beat.get("voice_text")),
            )
            priority = clean_text(beat.get("visual_priority") or "low").lower()
            wants_split = (
                duration >= policy["max_slot_duration_sec"]
                and len(must_items) >= 2
                and priority in {"high", "medium"}
            ) or (duration >= policy["max_slot_duration_sec"] + 1.5 and len(must_items) >= 2)
            slot_count = 1
            if wants_split:
                slot_count = min(3, max(2, len(must_items)))
                if duration / slot_count < policy["min_slot_duration_sec"]:
                    slot_count = max(1, int(duration // policy["min_slot_duration_sec"]))
                    slot_count = min(slot_count, len(must_items), 3) or 1
            windows = split_windows(start, end, slot_count)
            for local_index, (slot_start, slot_end) in enumerate(windows):
                item = must_items[min(local_index, len(must_items) - 1)] if must_items else clean_text(beat.get("voice_text"))
                slot_type = slot_type_for(beat, local_index, slot_count, beat_index)
                decision = decision_for_slot(slot_type, local_index)
                slot_priority = priority_for_slot(beat, local_index)
                slot_id = f"VS{len(slots) + 1:04d}"
                slots.append(
                    {
                        "visual_slot_id": slot_id,
                        "beat_ids": [beat.get("beat_id")],
                        "scene_ids": [beat.get("scene_id")],
                        "source_scene_id": beat.get("scene_id"),
                        "start": slot_start,
                        "end": slot_end,
                        "duration": round(slot_end - slot_start, 3),
                        "slot_type": slot_type,
                        "visual_function": clean_text(beat.get("beat_role") or scene.get("visual_function") or "show_spoken_idea"),
                        "must_show": [item],
                        "visualized_claim": clean_text(beat.get("spoken_claim") or scene.get("visualized_claim") or beat.get("voice_text")),
                        "generation_decision": decision,
                        "shot_design": clean_text(scene.get("composition") or slot_type.replace("_", " ")),
                        "priority": slot_priority,
                        "variant_count": variants_for(slot_priority, decision, project),
                        "film_block_id": clean_text(scene.get("film_block_id") or scene.get("global_scene_id") or scene.get("environment") or beat.get("beat_role") or f"block_{beat_index:04d}").lower().replace(" ", "_"),
                        "camera": clean_text(scene.get("camera") or "documentary cinematic framing"),
                        "lighting": clean_text(scene.get("lighting") or scene.get("lighting_family") or "motivated documentary lighting"),
                        "transition_in": "cut",
                        "transition_out": "cut_on_phrase_end",
                        "reason": "Visual slot adds a distinct observable idea from the narration beat." if slot_count > 1 else "Single purposeful visual slot covers this narration beat.",
                    }
                )
        return slots


class ExternalVisualAllocationAdapter:
    provider_name = "unified_llm_provider_v1"

    def __init__(self, project: dict[str, Any], repo_root: Path | None = None, override_mode: str | None = None, input_json: str | None = None) -> None:
        self.project = project
        self.repo_root = repo_root or Path(__file__).resolve().parents[1]
        self.config = provider_config_from_project(
            project,
            stage_name="author_visual_allocation_plan",
            override_mode=override_mode,
            input_json_path=input_json,
        )
        self.provider_name = f"complete_json:{self.config.mode}"

    def author_visual_slots(
        self,
        beats: list[dict[str, Any]],
        scene_plan: dict[str, Any],
        project: dict[str, Any],
        previous_errors: list[str] | None = None,
        previous_warnings: list[str] | None = None,
        previous_slots: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        context = build_visual_allocation_context(
            beats=beats,
            scene_plan=scene_plan,
            project=project,
            policy=policy_from_project(project),
            allowed_generation_decisions=sorted(ALLOWED_GENERATION_DECISIONS),
            allowed_slot_types=sorted(ALLOWED_SLOT_TYPES),
            previous_errors=previous_errors,
            previous_warnings=previous_warnings,
            previous_slots=previous_slots,
        )
        payload = complete_json(
            "author_visual_allocation_plan",
            "You are a visual director for a narrated silent-image pipeline. Return JSON only.",
            {
                "instruction": "Author the visual allocation plan from this context.",
                "user_prompt": build_json_only_prompt(
                    instruction="Author the visual allocation plan from this context.",
                    context=context,
                ),
                "context": context,
            },
            schema_name="visual_allocation_plan.v1",
            required_keys=["visual_slots"],
            provider_config=self.config,
        )
        rows = payload.get("visual_slots") or payload.get("slots") or payload.get("data") or []
        return [item for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []


def load_file_slots(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get("visual_slots", [])
    return []


def normalize_slot(raw: dict[str, Any], index: int, beat_by_id: dict[str, dict[str, Any]], scene_by_id: dict[str, dict[str, Any]], project: dict[str, Any]) -> dict[str, Any]:
    beat_ids = raw.get("beat_ids") or ([raw.get("beat_id")] if raw.get("beat_id") else [])
    beat_ids = [clean_text(item) for item in beat_ids if clean_text(item)]
    primary_beat = beat_by_id.get(beat_ids[0]) if beat_ids else {}
    source_scene_id = clean_text(raw.get("source_scene_id") or raw.get("scene_id") or (primary_beat or {}).get("scene_id"))
    scene_ids = raw.get("scene_ids") or ([source_scene_id] if source_scene_id else [])
    scene_ids = [clean_text(item) for item in scene_ids if clean_text(item)]
    scene = scene_by_id.get(source_scene_id, {})
    start = float(raw.get("start", (primary_beat or scene).get("start", 0)) or 0)
    end = float(raw.get("end", (primary_beat or scene).get("end", start)) or start)
    if end <= start:
        end = start + max(0.001, float(raw.get("duration", 0) or 0.001))
    decision = clean_text(raw.get("generation_decision") or raw.get("generation_mode") or "new_image").lower()
    if decision not in ALLOWED_GENERATION_DECISIONS:
        decision = "new_image"
    slot_type = clean_text(raw.get("slot_type") or decision or "explanation_visual").lower()
    if slot_type not in ALLOWED_SLOT_TYPES:
        slot_type = "explanation_visual"
    priority = clean_text(raw.get("priority") or raw.get("visual_priority") or (primary_beat or {}).get("visual_priority") or "low").lower()
    if priority not in {"high", "medium", "low"}:
        priority = "low"
    must_show = drawable_items(list(raw.get("must_show", []) or []), clean_text((primary_beat or {}).get("voice_text") or scene.get("voice_text")))
    return {
        "visual_slot_id": clean_text(raw.get("visual_slot_id") or f"VS{index:04d}"),
        "beat_ids": beat_ids,
        "scene_ids": scene_ids,
        "source_scene_id": source_scene_id,
        "start": round(start, 3),
        "end": round(end, 3),
        "duration": round(end - start, 3),
        "slot_type": slot_type,
        "visual_function": clean_text(raw.get("visual_function") or (primary_beat or {}).get("beat_role") or "show_spoken_idea"),
        "must_show": must_show,
        "visualized_claim": clean_text(raw.get("visualized_claim") or (primary_beat or {}).get("spoken_claim") or scene.get("visualized_claim") or (primary_beat or {}).get("voice_text")),
        "generation_decision": decision,
        "source_visual_slot_id": clean_text(raw.get("source_visual_slot_id") or raw.get("source_frame_id")),
        "shot_design": clean_text(raw.get("shot_design") or raw.get("shot_type") or slot_type.replace("_", " ")),
        "priority": priority,
        "variant_count": int(raw.get("variant_count", variants_for(priority, decision, project)) or 0),
        "film_block_id": clean_text(raw.get("film_block_id") or scene.get("film_block_id") or scene.get("global_scene_id") or f"block_{index:04d}"),
        "camera": clean_text(raw.get("camera") or scene.get("camera") or "documentary cinematic framing"),
        "lighting": clean_text(raw.get("lighting") or scene.get("lighting") or scene.get("lighting_family") or "motivated documentary lighting"),
        "transition_in": clean_text(raw.get("transition_in") or "cut"),
        "transition_out": clean_text(raw.get("transition_out") or "cut_on_phrase_end"),
        "reason": clean_text(raw.get("reason") or "Authored visual allocation slot."),
    }


def validate_slots(slots: list[dict[str, Any]], beats: list[dict[str, Any]], policy: dict[str, float]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    beat_by_id = {clean_text(beat.get("beat_id")): beat for beat in beats if clean_text(beat.get("beat_id"))}
    seen = set()
    slots_by_beat: dict[str, list[dict[str, Any]]] = {beat_id: [] for beat_id in beat_by_id}
    previous_end = None
    for slot in slots:
        slot_id = clean_text(slot.get("visual_slot_id"))
        if not slot_id:
            errors.append("visual slot missing visual_slot_id")
            continue
        if slot_id in seen:
            errors.append(f"duplicate visual_slot_id: {slot_id}")
        seen.add(slot_id)
        start = float(slot.get("start", 0) or 0)
        end = float(slot.get("end", 0) or 0)
        duration = float(slot.get("duration", end - start) or 0)
        if end <= start or duration <= 0:
            errors.append(f"{slot_id} has invalid timing")
        if duration < 0.6:
            errors.append(f"{slot_id} is too short for a readable visual slot")
        elif duration < policy["min_slot_duration_sec"]:
            warnings.append(f"{slot_id} is shorter than visual cadence policy")
        if duration > policy["max_static_hold_sec"] and slot.get("generation_decision") in {"hold_previous", "continuation_motion"}:
            errors.append(f"{slot_id} holds/continues too long without a new visual")
        if previous_end is not None:
            if start < previous_end - 0.08:
                errors.append(f"{slot_id} overlaps previous visual slot")
            elif start > previous_end + 0.12:
                warnings.append(f"{slot_id} introduces a visual allocation gap")
        previous_end = max(previous_end or end, end)
        decision = clean_text(slot.get("generation_decision")).lower()
        if decision not in ALLOWED_GENERATION_DECISIONS:
            errors.append(f"{slot_id} unsupported generation_decision `{decision}`")
        if decision in {"new_image", "new_angle_same_setup", "detail_insert", "reaction_shot", "establishing_shot", "manual_asset"} and int(slot.get("variant_count", 0) or 0) <= 0:
            errors.append(f"{slot_id} requires at least one planned variant")
        if decision in {"hold_previous", "continuation_motion"} and int(slot.get("variant_count", 0) or 0) != 0:
            warnings.append(f"{slot_id} is non-generative but variant_count is not zero")
        if not isinstance(slot.get("must_show", []), list) or not [item for item in slot.get("must_show", []) if clean_text(item)]:
            errors.append(f"{slot_id} missing concrete must_show")
        for item in slot.get("must_show", []) or []:
            text = clean_text(item)
            if text.lower() in ABSTRACT_ONLY_TERMS or is_probably_abstract(text):
                errors.append(f"{slot_id} has abstract must_show: {text}")
        beat_ids = slot.get("beat_ids", [])
        if not isinstance(beat_ids, list) or not beat_ids:
            errors.append(f"{slot_id} missing beat_ids")
            continue
        for beat_id in beat_ids:
            beat_id = clean_text(beat_id)
            if beat_id not in beat_by_id:
                errors.append(f"{slot_id} points to unknown beat_id {beat_id}")
            else:
                beat = beat_by_id[beat_id]
                beat_start = float(beat.get("start", 0) or 0)
                beat_end = float(beat.get("end", 0) or 0)
                if start < beat_start - 0.12 or end > beat_end + 0.12:
                    warnings.append(f"{slot_id} extends outside {beat_id}; this is allowed only for deliberate multi-beat slots")
                slots_by_beat.setdefault(beat_id, []).append(slot)
    for beat_id, beat in beat_by_id.items():
        beat_slots = sorted(slots_by_beat.get(beat_id, []), key=lambda item: float(item.get("start", 0) or 0))
        if not beat_slots:
            errors.append(f"{beat_id} is not covered by any visual slot")
            continue
        beat_start = float(beat.get("start", 0) or 0)
        beat_end = float(beat.get("end", 0) or 0)
        if float(beat_slots[0].get("start", 0) or 0) > beat_start + 0.12:
            errors.append(f"{beat_id} visual coverage starts late")
        if float(beat_slots[-1].get("end", 0) or 0) < beat_end - 0.12:
            errors.append(f"{beat_id} visual coverage ends early")
    return errors, warnings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--input-json", help="Optional authored visual_allocation_plan payload to normalize into the project path.")
    parser.add_argument("--provider", choices=["heuristic", "disabled", "file", "external", "command", "http", "openai_compatible"], help="Visual allocation authoring provider.")
    parser.add_argument("--max-repair-attempts", type=int, default=None, help="External LLM repair attempts after Python validation errors.")
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    scene_plan_path = Path(project["scene_plan"]["scene_plan_path"])
    beats_path = Path(project["planning"]["narration_beats_path"])
    output_path = Path(project["planning"]["visual_allocation_plan_path"])
    if not beats_path.exists():
        raise FileNotFoundError(f"Authored narration beats missing: {beats_path}")
    scene_plan = load_json(scene_plan_path)
    beats_payload = load_json(beats_path)
    beats = beats_payload.get("beats", [])
    scene_by_id = {scene.get("scene_id"): scene for scene in scene_plan.get("scenes", []) if scene.get("scene_id")}
    beat_by_id = {beat.get("beat_id"): beat for beat in beats if beat.get("beat_id")}
    provider = provider_from_project(project, args.provider, has_input_json=bool(args.input_json))
    policy = policy_from_project(project)
    provider_name = provider
    repair_attempts: list[dict[str, Any]] = []

    if provider == "file":
        if not args.input_json:
            raise RuntimeError("--provider file requires --input-json")
        raw_slots = load_file_slots(Path(args.input_json).resolve())
        slots = [normalize_slot(slot, index, beat_by_id, scene_by_id, project) for index, slot in enumerate(raw_slots, start=1)]
        errors, warnings = validate_slots(slots, beats, policy)
        provider_name = "file"
    elif provider in {"command", "http", "openai_compatible"}:
        adapter = ExternalVisualAllocationAdapter(project, repo_root=Path(__file__).resolve().parents[1], override_mode=provider)
        provider_name = adapter.provider_name
        configured_attempts = project.get("planning", {}).get("visual_allocation_llm", {}).get("max_repair_attempts")
        max_repair_attempts = args.max_repair_attempts if args.max_repair_attempts is not None else int(configured_attempts if configured_attempts is not None else 1)
        previous_errors: list[str] = []
        previous_warnings: list[str] = []
        previous_slots: list[dict[str, Any]] = []
        raw_slots: list[dict[str, Any]] = []
        slots: list[dict[str, Any]] = []
        errors: list[str] = []
        warnings: list[str] = []
        for attempt in range(max_repair_attempts + 1):
            raw_slots = adapter.author_visual_slots(
                beats,
                scene_plan,
                project,
                previous_errors=previous_errors,
                previous_warnings=previous_warnings,
                previous_slots=previous_slots,
            )
            slots = [normalize_slot(slot, index, beat_by_id, scene_by_id, project) for index, slot in enumerate(raw_slots, start=1)]
            errors, warnings = validate_slots(slots, beats, policy)
            repair_attempts.append(
                {
                    "attempt": attempt + 1,
                    "status": "passed" if not errors else "failed",
                    "error_count": len(errors),
                    "warning_count": len(warnings),
                    "errors": errors[:20],
                    "warnings": warnings[:20],
                }
            )
            if not errors:
                break
            previous_errors = errors
            previous_warnings = warnings
            previous_slots = slots
    else:
        raw_slots = HeuristicVisualAllocationAdapter().author_visual_slots(beats, scene_plan, project)
        slots = [normalize_slot(slot, index, beat_by_id, scene_by_id, project) for index, slot in enumerate(raw_slots, start=1)]
        errors, warnings = validate_slots(slots, beats, policy)
        provider_name = HeuristicVisualAllocationAdapter.provider_name

    if errors:
        raise RuntimeError("Invalid visual allocation plan:\n" + "\n".join(errors))
    payload = {
        "project_id": project.get("project_id"),
        "provider": provider,
        "provider_name": provider_name,
        "planning_source": "narration_beats.json",
        "visual_cadence_policy": policy,
        "warnings": warnings,
        "repair_attempts": repair_attempts,
        "metrics": {
            "narration_beats_count": len(beats),
            "visual_slots_count": len(slots),
            "new_image_slots_count": sum(1 for slot in slots if slot.get("generation_decision") not in {"hold_previous", "continuation_motion"}),
            "hold_or_continuation_slots_count": sum(1 for slot in slots if slot.get("generation_decision") in {"hold_previous", "continuation_motion"}),
            "planned_variants_count": sum(int(slot.get("variant_count", 0) or 0) for slot in slots),
            "average_slot_duration": round(sum(float(slot.get("duration", 0) or 0) for slot in slots) / len(slots), 4) if slots else 0.0,
        },
        "visual_slots": slots,
    }
    save_json(output_path, payload)
    project["planning"]["visual_allocation_plan_path"] = str(output_path)
    project["planning"]["visual_allocation_status"] = "authored"
    project["planning"]["visual_allocation_provider"] = provider
    project["current_stage"] = "estimate_project_generation"
    save_project(project_json, project)
    print(output_path)


if __name__ == "__main__":
    main()
