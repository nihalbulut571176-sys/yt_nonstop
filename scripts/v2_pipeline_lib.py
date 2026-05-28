import argparse
import json
import math
from pathlib import Path
from typing import Any

from build_project_scene_plan import merge_into_sentence_blocks, parse_srt
from pipeline_contracts import (
    V2StoryboardFrame,
    build_reference_prefix,
    contains_forbidden_terms,
    count_pattern_breaks,
    format_srt_timestamp,
    has_cyrillic,
    normalize_text,
    normalize_text_lower,
    prompt_length_ok,
    similarity_score,
    stable_hash,
    write_csv,
)
from project_pipeline_utils import load_json, load_project, save_json, save_project


DEFAULT_NEGATIVE_PROMPT = (
    "text, subtitles, logos, watermark, fake UI, distorted hands, plastic skin, glamorized criminal hero shot"
)

ENGLISH_SCENE_PATTERNS = [
    (("ювелир", "бутик"), ("luxury jewelry boutique interior", "luxury retail security", "a high-value boutique presented as an untouchable space")),
    (("камер", "потолк"), ("ceiling surveillance cameras and locked entry", "security architecture", "the store feels watched from above and controlled by design")),
    (("магнитн", "замк"), ("magnetic security locks on the entrance", "access control system", "entry itself becomes a delayed decision point")),
    (("охран", "стекл"), ("guarded glass barrier and protected display zone", "guarded showroom perimeter", "confidence in protection makes the place feel invulnerable")),
    (("с улицы", "камня"), ("distance between an ordinary passerby and rare stones", "luxury distance", "wealth is protected through architecture and intimidation")),
    (("входят двое",), ("two calm entrants crossing the boutique threshold", "entry choreography", "the operation begins without visible aggression")),
    (("состоятельн", "клиент"), ("wealthy-looking customers blending into the showroom", "social camouflage", "appearance hides operational intent")),
    (("видел витрину",), ("operator studying the display layout in advance", "pre-visit reconnaissance", "the theft succeeds before the theft begins")),
    (("колье", "кам-тес-де-ван-дом"), ("legendary diamond necklace in a premium display", "target object", "the target is defined with precision and status")),
    (("30 миллионов", "116 бриллиант"), ("museum-grade necklace with dozens of diamonds", "high-value jewel object", "the object alone explains the scale of the risk")),
    (("100 карат",), ("massive central diamond stone under boutique lighting", "gem detail", "value is concentrated in one impossible object")),
    (("считанные секунды",), ("compressed heist timing measured in seconds", "time pressure", "speed defeats reaction time")),
    (("газ", "драгоцен"), ("employee blinded by spray as the display opens", "attack and extraction", "violence is used only to clear the final obstruction")),
    (("преступники уже уходят",), ("operators leaving while bystanders still process the event", "human delay", "people react after the crucial moment has already passed")),
    (("токио", "2004"), ("Tokyo city context in 2004", "historical archive", "the case belongs to real history rather than movie fantasy")),
    (("полицию", "разных стран"), ("international police pressure across multiple countries", "institutional pressure", "the case forces systems to acknowledge a new type of threat")),
    (("двигаются быстрее", "система"), ("operators moving faster than institutional response", "response lag", "the system loses because it decides too slowly")),
    (("розовыми пантерами",), ("the Pink Panthers identity entering public language", "identity reveal", "a criminal myth is born from concrete evidence")),
    (("единая форма", "штаб"), ("absence of uniforms or headquarters behind the myth", "myth rejection", "the network works without theatrical identity markers")),
    (("название", "другого эпизода"), ("nickname born from a later theft episode", "media framing", "the myth grows from narrative coincidence")),
    (("баночке с кремом",), ("stolen diamond hidden inside a cream jar", "concealed evidence", "the network favors practical concealment over glamour")),
    (("старом фильме", "пантер"), ("cultural echo of an old Pink Panther film", "pop-culture echo", "the nickname sounds playful while the mechanism is deadly serious")),
    (("некомедия",), ("dark reality behind a seemingly ironic nickname", "tone reversal", "humor in the label hides severity in the method")),
    (("балкан", "военн"), ("Balkan network of ex-soldiers and logistics specialists", "transnational network", "professional backgrounds make the network operationally resilient")),
    (("логистик",), ("logistics specialists treating theft like engineering", "operational engineering", "robbery becomes a systems problem rather than an impulse crime")),
    (("разберем", "механизм"), ("forensic breakdown of the criminal mechanism", "investigative mechanism", "the story shifts from legend to operational analysis")),
    (("выбирали цели",), ("target selection logic inside the robbery network", "target selection", "choice of target is a strategic discipline")),
    (("архитектур", "бюрократ"), ("architecture, human reaction, and bureaucracy used as tools", "system exploitation", "the crew weaponizes the environment instead of brute force")),
    (("ловили", "сеть"), ("arrests failing to erase the wider network", "network persistence", "individual captures do not dissolve the system behind them")),
]


def _project_json_from_args(args: argparse.Namespace) -> Path:
    return Path(args.project_json).resolve()


def _load_scene_plan(project: dict[str, Any]) -> list[dict[str, Any]]:
    scene_plan_path = Path(project["scene_plan"]["scene_plan_path"])
    payload = load_json(scene_plan_path)
    return payload.get("scenes", [])


def _load_storyboard_frames(project: dict[str, Any]) -> list[dict[str, Any]]:
    storyboard_frames_path = Path(project["planning"]["storyboard_frames_path"])
    if not storyboard_frames_path.exists():
        return []
    payload = load_json(storyboard_frames_path)
    return payload.get("frames", payload if isinstance(payload, list) else [])


def _save_storyboard_frames(project: dict[str, Any], frames: list[dict[str, Any]]) -> None:
    payload = {"project_id": project["project_id"], "frame_count": len(frames), "frames": frames}
    save_json(Path(project["planning"]["storyboard_frames_path"]), payload)


def _load_global_scenes(project: dict[str, Any]) -> list[dict[str, Any]]:
    path = Path(project["planning"]["global_scene_plan_path"])
    if not path.exists():
        return []
    return load_json(path).get("scenes", [])


def _load_subscenes(project: dict[str, Any]) -> list[dict[str, Any]]:
    path = Path(project["planning"]["subscene_plan_path"])
    if not path.exists():
        return []
    return load_json(path).get("subscenes", [])


def _scene_excerpt(text: str, limit: int = 72) -> str:
    clean = normalize_text(text)
    return clean[:limit].rstrip() + ("..." if len(clean) > limit else "")


def _pick_visual_function(index: int, count: int) -> str:
    if index == 0:
        return "hook"
    if index == count - 1:
        return "payoff"
    if index % 7 == 0:
        return "pattern_break"
    if index % 3 == 0:
        return "evidence"
    return "explain"


def _pick_mini_world(scene: dict[str, Any], index: int) -> str:
    candidates = [
        scene.get("environment", ""),
        scene.get("visual_strategy", ""),
        scene.get("event_type", ""),
        scene.get("scene_meaning", ""),
        scene.get("voice_text", ""),
    ]
    for candidate in candidates:
        clean = normalize_text(candidate)
        if clean:
            lowered = clean.lower()
            if "camera" in lowered or "security" in lowered:
                return "security architecture"
            if "archive" in lowered or "history" in lowered:
                return "historical archive"
            if "escape" in lowered or "operator" in lowered:
                return "human delay"
            return clean[:48]
    fallback_worlds = [
        "security architecture",
        "human delay",
        "forensic detail",
        "urban consequence",
        "institutional pressure",
    ]
    return fallback_worlds[index % len(fallback_worlds)]


def _englishize_scene_fields(scene: dict[str, Any], visual_function: str) -> tuple[str, str, str]:
    voice_text = normalize_text(scene.get("voice_text", ""))
    lowered = voice_text.lower()
    for keywords, values in ENGLISH_SCENE_PATTERNS:
        if all(keyword in lowered for keyword in keywords):
            return values
    fallback_subjects = {
        "hook": "high-stakes documentary opening inside a controlled luxury space",
        "evidence": "forensic documentary clue that makes the mechanism legible",
        "pattern_break": "unexpected visual turn that interrupts repetition",
        "payoff": "closing investigative image that resolves the beat",
        "explain": "clear documentary image that advances the mechanism",
    }
    subject = fallback_subjects.get(visual_function, "clear documentary image")
    mini_world = {
        "hook": "luxury retail security",
        "evidence": "forensic detail",
        "pattern_break": "investigative contrast",
        "payoff": "documentary resolution",
        "explain": "investigative world",
    }.get(visual_function, "investigative world")
    meaning = {
        "hook": "the world looks perfect until timing defeats it",
        "evidence": "a concrete clue turns abstraction into physical reality",
        "pattern_break": "the sequence needs a distinct shift to stay legible",
        "payoff": "the image should complete the current narrative beat",
        "explain": "the image should make the narration operationally clear",
    }.get(visual_function, "the image should carry the story forward")
    return subject, mini_world, meaning


def _rebuild_prompt(frame: dict[str, Any], variant_note: str = "") -> str:
    subject = normalize_text(frame.get("main_subject") or "documentary evidence moment")
    mini_world = normalize_text(frame.get("mini_world") or "investigative world")
    why = normalize_text(frame.get("why_this_frame_exists") or "advance the narrative with a distinct documentary beat")
    function = normalize_text(frame.get("visual_function") or "documentary beat")
    note = f" {variant_note.strip()}" if variant_note.strip() else ""
    return normalize_text(
        (
            "Premium cinematic documentary still, 16:9. "
            f"{subject}, inside {mini_world}, visual function {function}. "
            f"Frame purpose: {why}. "
            "Realistic textures, investigative realism, no lettering, silent documentary image, no speaking characters."
            f"{note}"
        )
    )


def _load_subject_registry(project: dict[str, Any]) -> dict[str, dict[str, Any]]:
    registry_path = Path(project["prompts"].get("subject_registry_path") or "")
    if not registry_path.exists():
        return {}
    payload = load_json(registry_path)
    return {item["subject_id"]: item for item in payload.get("subjects", []) if item.get("subject_id")}


def _infer_subject_ids_for_frame(frame: dict[str, Any], known_subject_ids: set[str]) -> list[str]:
    haystack = " ".join(
        [
            normalize_text_lower(frame.get("main_subject", "")),
            normalize_text_lower(frame.get("mini_world", "")),
            normalize_text_lower(frame.get("scene_meaning", "")),
            normalize_text_lower(frame.get("why_this_frame_exists", "")),
            normalize_text_lower(frame.get("voice_text", "")),
        ]
    )
    subjects: list[str] = []
    if "lead_operator" in known_subject_ids or "support_operator" in known_subject_ids:
        if any(marker in haystack for marker in ("two calm entrants", "wealthy-looking customers", "operators leaving", "operators moving", "social camouflage", "entry choreography")):
            if "lead_operator" in known_subject_ids:
                subjects.append("lead_operator")
            if "support_operator" in known_subject_ids:
                subjects.append("support_operator")
        elif any(marker in haystack for marker in ("operator studying", "pre-visit reconnaissance", "scout", "display layout")):
            if "lead_operator" in known_subject_ids:
                subjects.append("lead_operator")
    if "security_guard" in known_subject_ids and any(marker in haystack for marker in ("guarded showroom", "security architecture", "security guard", "guarded glass barrier")):
        subjects.append("security_guard")
    if "boutique_attendant" in known_subject_ids and any(marker in haystack for marker in ("employee blinded", "boutique attendant", "staff", "display opens")):
        subjects.append("boutique_attendant")
    deduped: list[str] = []
    for subject_id in subjects:
        if subject_id not in deduped:
            deduped.append(subject_id)
    return deduped


def _fastgen_block_for_frame(frame: dict[str, Any]) -> str:
    prompt = normalize_text(frame.get("image_prompt_final", ""))
    if not prompt:
        return "No character reference."
    prefix = build_reference_prefix(list(frame.get("reference_ids", [])))
    return f"{prefix} {prompt}".strip()


def _reference_payload_for_frame(frame: dict[str, Any], subject_registry: dict[str, dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    subject_ids = _infer_subject_ids_for_frame(frame, set(subject_registry))
    reference_ids: list[str] = []
    reference_bindings: list[dict[str, Any]] = []
    for index, subject_id in enumerate(subject_ids):
        subject = subject_registry.get(subject_id)
        if not subject:
            continue
        asset_ids = list(subject.get("reference_asset_ids", []))
        if not asset_ids:
            continue
        identity_sheet_assets = [asset_id for asset_id in asset_ids if "identity_sheet" in asset_id.lower() or asset_id.lower().endswith("_sheet")]
        if identity_sheet_assets:
            chosen = identity_sheet_assets[:1]
        elif len(subject_ids) > 1:
            chosen = asset_ids[:1]
        elif "wardrobe" in " ".join(asset_ids).lower():
            wardrobe = [asset_id for asset_id in asset_ids if "wardrobe" in asset_id.lower()]
            chosen = wardrobe[:1] or asset_ids[:1]
        else:
            chosen = asset_ids[:1]
        reference_ids.extend(chosen)
        reference_bindings.append(
            {
                "subject_id": subject_id,
                "reference_asset_ids": chosen,
                "usage": "identity_sheet" if identity_sheet_assets else "identity_and_wardrobe",
                "strength": "strict" if index == 0 and len(subject_ids) == 1 else "medium",
            }
        )
    return reference_ids, reference_bindings


def build_v2_project_skeleton(project_json: Path) -> Path:
    project_json = Path(project_json).resolve()
    project = load_project(project_json)
    srt_path = Path(project["scene_plan"]["source_srt_path"] or project["transcription"]["srt_path"])
    if not srt_path.exists():
        raise FileNotFoundError(f"SRT not found: {srt_path}")
    segments = parse_srt(srt_path.read_text(encoding="utf-8-sig"))
    sentence_blocks = merge_into_sentence_blocks(segments)
    scenes = _load_scene_plan(project)
    payload = {
        "project_id": project["project_id"],
        "source_files": {
            "script": project.get("inputs", {}).get("raw_text_path"),
            "srt": str(srt_path),
        },
        "sentence_blocks": sentence_blocks,
        "scene_ids": [scene["scene_id"] for scene in scenes],
        "frame_count": len(scenes),
        "scenes": [],
        "frames": [],
    }
    path = Path(project["planning"]["v2_project_skeleton_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    save_json(path, payload)
    project["planning"]["status"] = "v2_skeleton_built"
    project["current_stage"] = "build_scenes"
    save_project(project_json, project)
    return path


def build_v2_global_scenes(project_json: Path, target_scenes: int | None = None) -> Path:
    project_json = Path(project_json).resolve()
    project = load_project(project_json)
    scenes = _load_scene_plan(project)
    if not scenes:
        raise RuntimeError("scene_plan.json contains no scenes")
    target = int(target_scenes or project["planning"].get("v2_target_scene_count") or 15)
    chunk_size = max(1, math.ceil(len(scenes) / target))
    global_scenes = []
    for index, start_idx in enumerate(range(0, len(scenes), chunk_size), start=1):
        chunk = scenes[start_idx : start_idx + chunk_size]
        global_scene_id = f"S{index:02d}"
        start = float(chunk[0]["start"])
        end = float(chunk[-1]["end"])
        global_scenes.append(
            {
                "scene_id": global_scene_id,
                "title": _scene_excerpt(chunk[0].get("scene_summary") or chunk[0]["voice_text"]),
                "start_time": format_srt_timestamp(start).replace(",", "."),
                "end_time": format_srt_timestamp(end).replace(",", "."),
                "start": start,
                "end": end,
                "scene_function": "sequence_block" if index > 1 else "cold_open",
                "semantic_thesis": _scene_excerpt(" ".join(item.get("scene_meaning") or item["voice_text"] for item in chunk), 110),
                "target_frame_count": len(chunk),
                "child_scene_ids": [item["scene_id"] for item in chunk],
            }
        )
    path = Path(project["planning"]["global_scene_plan_path"])
    save_json(path, {"project_id": project["project_id"], "scene_count": len(global_scenes), "scenes": global_scenes})
    project["planning"]["status"] = "v2_global_scenes_built"
    project["current_stage"] = "build_subscenes"
    save_project(project_json, project)
    return path


def build_v2_subscenes(project_json: Path) -> Path:
    project_json = Path(project_json).resolve()
    project = load_project(project_json)
    global_scenes = _load_global_scenes(project)
    scenes = {scene["scene_id"]: scene for scene in _load_scene_plan(project)}
    subscenes = []
    for global_scene in global_scenes:
        child_ids = global_scene.get("child_scene_ids", [])
        if not child_ids:
            continue
        child_chunk_size = max(1, math.ceil(len(child_ids) / max(1, min(4, len(child_ids)))))
        for sub_index, offset in enumerate(range(0, len(child_ids), child_chunk_size), start=1):
            members = child_ids[offset : offset + child_chunk_size]
            first_scene = scenes[members[0]]
            subscene_id = f"{global_scene['scene_id']}_SS{sub_index:02d}"
            function = _pick_visual_function(sub_index - 1, max(1, len(child_ids) // child_chunk_size))
            subscenes.append(
                {
                    "subscene_id": subscene_id,
                    "scene_id": global_scene["scene_id"],
                    "title": _scene_excerpt(first_scene.get("scene_summary") or first_scene["voice_text"], 54),
                    "function": function,
                    "visual_conflict": "precision versus uncertainty",
                    "screen_action": _scene_excerpt(first_scene["voice_text"], 96),
                    "motion_feeling": "controlled tension",
                    "transition_to_next": "shift the visual logic without changing the timing truth",
                    "target_frame_count": len(members),
                    "child_scene_ids": members,
                }
            )
    path = Path(project["planning"]["subscene_plan_path"])
    save_json(path, {"project_id": project["project_id"], "subscene_count": len(subscenes), "subscenes": subscenes})
    project["planning"]["status"] = "v2_subscenes_built"
    project["current_stage"] = "build_storyboard"
    save_project(project_json, project)
    return path


def build_v2_storyboard(project_json: Path) -> Path:
    project_json = Path(project_json).resolve()
    project = load_project(project_json)
    scenes = _load_scene_plan(project)
    global_scenes = _load_global_scenes(project)
    subscenes = _load_subscenes(project)
    global_scene_lookup = {
        child_scene_id: global_scene["scene_id"]
        for global_scene in global_scenes
        for child_scene_id in global_scene.get("child_scene_ids", [])
    }
    subscene_lookup = {
        child_scene_id: subscene["subscene_id"]
        for subscene in subscenes
        for child_scene_id in subscene.get("child_scene_ids", [])
    }
    frames: list[dict[str, Any]] = []
    for index, scene in enumerate(scenes):
        frame_id = f"{scene['scene_id'].replace('scene_', 'F')}"
        visual_function = _pick_visual_function(index, len(scenes))
        subject_en, mini_world_en, meaning_en = _englishize_scene_fields(scene, visual_function)
        mini_world = mini_world_en if has_cyrillic(_pick_mini_world(scene, index)) else _pick_mini_world(scene, index)
        subject = subject_en
        meaning = meaning_en
        why = normalize_text(
            scene.get("visual_reason")
            or scene.get("visual_goal")
            or f"Turn the narration into a distinct {visual_function} image with a fresh investigative purpose."
        )
        if has_cyrillic(why):
            why = f"Turn the narration into a distinct {visual_function} image with a fresh investigative purpose."
        frame = V2StoryboardFrame(
            frame_id=frame_id,
            scene_id=scene["scene_id"],
            subscene_id=subscene_lookup.get(scene["scene_id"], "UNASSIGNED_SUBSCENE"),
            global_scene_id=global_scene_lookup.get(scene["scene_id"], "UNASSIGNED_SCENE"),
            start_time=format_srt_timestamp(float(scene["start"])).replace(",", "."),
            end_time=format_srt_timestamp(float(scene["end"])).replace(",", "."),
            duration_sec=float(scene["duration"]),
            voice_text=scene["voice_text"],
            visual_function=visual_function,
            mini_world=mini_world,
            scene_meaning=meaning,
            main_subject=subject[:140],
            why_this_frame_exists=why,
            director_prompt={
                "scene_meaning": meaning,
                "visual_intent": normalize_text(scene.get("visual_idea") or subject),
                "risk_note": "Avoid readable text and fake UI.",
                "why_this_frame_exists": why,
            },
            image_prompt_final="",
            negative_prompt=scene.get("negative_prompt") or DEFAULT_NEGATIVE_PROMPT,
            dc_status="pending",
            qc_flags=[],
        )
        frames.append(frame.__dict__)
    _save_storyboard_frames(project, frames)
    project["planning"]["status"] = "v2_storyboard_built"
    project["current_stage"] = "directors_cut"
    save_project(project_json, project)
    return Path(project["planning"]["storyboard_frames_path"])


def run_v2_directors_cut(project_json: Path, chunk_size: int | None = None) -> Path:
    project_json = Path(project_json).resolve()
    project = load_project(project_json)
    frames = _load_storyboard_frames(project)
    size = int(chunk_size or project["planning"].get("v2_chunk_size") or 30)
    reviews = []
    previous = None
    for frame in frames:
        problems = []
        if previous is not None and similarity_score(previous.get("main_subject", ""), frame.get("main_subject", "")) > 85:
            problems.append("Too similar to previous frame subject.")
        if previous is not None and frame.get("mini_world") == previous.get("mini_world"):
            problems.append("Mini-world repeats without a clear break.")
        if not normalize_text(frame.get("why_this_frame_exists", "")):
            problems.append("Missing visual reason to exist.")
        frame["dc_status"] = "rewrite" if problems else "approved"
        reviews.append(
            {
                "frame_id": frame["frame_id"],
                "dc_status": frame["dc_status"],
                "problem": "; ".join(problems),
                "fix": "Shift mini-world or subject emphasis while preserving timing." if problems else "",
            }
        )
        previous = frame
    chunks = []
    for start in range(0, len(frames), size):
        chunk_frames = frames[start : start + size]
        chunks.append(
            {
                "chunk_index": len(chunks) + 1,
                "frame_ids": [item["frame_id"] for item in chunk_frames],
                "start_frame_id": chunk_frames[0]["frame_id"],
                "end_frame_id": chunk_frames[-1]["frame_id"],
            }
        )
    _save_storyboard_frames(project, frames)
    path = Path(project["prompts"]["directors_cut_review_path"])
    save_json(path, {"project_id": project["project_id"], "chunk_size": size, "chunks": chunks, "frames": reviews})
    project["prompts"]["status"] = "directors_cut_reviewed"
    project["current_stage"] = "write_prompts"
    save_project(project_json, project)
    return path


def write_v2_prompts(project_json: Path) -> Path:
    project_json = Path(project_json).resolve()
    project = load_project(project_json)
    frames = _load_storyboard_frames(project)
    review_path = Path(project["prompts"]["directors_cut_review_path"])
    subject_registry = _load_subject_registry(project)
    review_lookup = {}
    if review_path.exists():
        review_lookup = {item["frame_id"]: item for item in load_json(review_path).get("frames", [])}
    llm_drafts = []
    final_scene_plan_scenes = []
    for frame in frames:
        review = review_lookup.get(frame["frame_id"], {})
        variant_note = "Introduce a stronger pattern break." if review.get("dc_status") == "rewrite" else ""
        frame["image_prompt_final"] = _rebuild_prompt(frame, variant_note=variant_note)
        frame["negative_prompt"] = frame.get("negative_prompt") or DEFAULT_NEGATIVE_PROMPT
        reference_ids, reference_bindings = _reference_payload_for_frame(frame, subject_registry)
        frame["reference_ids"] = reference_ids
        frame["reference_bindings"] = reference_bindings
        frame["director_prompt"] = frame.get("director_prompt") or {
            "scene_meaning": frame.get("scene_meaning", ""),
            "visual_intent": frame.get("main_subject", ""),
            "risk_note": "Avoid readable text and fake UI.",
            "why_this_frame_exists": frame.get("why_this_frame_exists", ""),
        }
        llm_drafts.append(
            {
                "scene_id": frame["scene_id"],
                "frame_id": frame["frame_id"],
                "beat_id": frame.get("beat_id", frame["scene_id"].replace("scene_", "beat_")),
                "subscene_id": frame["subscene_id"],
                "global_scene_id": frame["global_scene_id"],
                "visual_goal": frame["director_prompt"]["visual_intent"],
                "visualized_claim": frame["director_prompt"].get("scene_meaning", frame["why_this_frame_exists"]),
                "final_prompt": frame["image_prompt_final"],
                "negative_prompt": frame["negative_prompt"],
                "reference_ids": reference_ids,
                "reference_bindings": reference_bindings,
                "must_not_show": ["different recurring face", "readable text", "fake UI"],
                "mini_world": frame["mini_world"],
                "why_this_frame_exists": frame["why_this_frame_exists"],
                "dc_status": frame["dc_status"],
            }
        )
        final_scene_plan_scenes.append(
            {
                "scene_id": frame["scene_id"],
                "start": frame["start_time"],
                "end": frame["end_time"],
                "duration": frame["duration_sec"],
                "voice_text": frame["voice_text"],
                "subscene_id": frame["subscene_id"],
                "global_scene_id": frame["global_scene_id"],
                "mini_world": frame["mini_world"],
                "why_this_frame_exists": frame["why_this_frame_exists"],
                "director_prompt": frame["director_prompt"],
                "image_prompt_final": frame["image_prompt_final"],
                "final_prompt": frame["image_prompt_final"],
                "prompt": frame["image_prompt_final"],
                "negative_prompt": frame["negative_prompt"],
                "reference_ids": reference_ids,
                "reference_bindings": reference_bindings,
                "dc_status": frame["dc_status"],
                "qc_flags": frame.get("qc_flags", []),
            }
        )
    _save_storyboard_frames(project, frames)
    save_json(Path(project["prompts"]["llm_prompt_drafts_path"]), llm_drafts)
    save_json(Path(project["prompts"]["prompt_package_path"]), {"project_id": project["project_id"], "items": llm_drafts})
    save_json(Path(project["prompts"]["final_scene_plan_path"]), {"project_id": project["project_id"], "scenes": final_scene_plan_scenes})
    export_lines = [_fastgen_block_for_frame(frame) for frame in frames]
    Path(project["prompts"]["fastgen_export_path"]).write_text("\n\n".join(export_lines) + "\n", encoding="utf-8")
    project["prompts"]["status"] = "v2_prompts_written"
    project["current_stage"] = "qc"
    save_project(project_json, project)
    return Path(project["prompts"]["prompt_package_path"])


def run_v2_qc(project_json: Path, similarity_threshold: int = 85) -> Path:
    project_json = Path(project_json).resolve()
    project = load_project(project_json)
    frames = _load_storyboard_frames(project)
    rewrite_items = []
    duplicate_rows = []
    weak_rows = []
    report_lines = ["# V2 QC Report", ""]
    mini_world_streak = 0
    subject_streak = 0
    previous = None
    family_counts: dict[str, int] = {}

    for frame in frames:
        flags = set(frame.get("qc_flags", []))
        prompt = frame.get("image_prompt_final", "")
        if not prompt_length_ok(prompt):
            flags.add("prompt_too_long")
        if not normalize_text(frame.get("negative_prompt", "")):
            flags.add("missing_negative_prompt")
        if has_cyrillic(prompt):
            flags.add("cyrillic_in_prompt")
        for term in contains_forbidden_terms(prompt):
            flags.add(f"forbidden:{term}")
        family_key = normalize_text_lower(prompt)
        family_counts[family_key] = family_counts.get(family_key, 0) + 1

        if previous is not None:
            if similarity_score(previous.get("image_prompt_final", ""), prompt) >= similarity_threshold:
                flags.add("possible_duplicate_prompt")
                duplicate_rows.append(
                    {
                        "frame_id": frame["frame_id"],
                        "other_frame_id": previous["frame_id"],
                        "similarity": similarity_score(previous.get("image_prompt_final", ""), prompt),
                        "reason": "adjacent prompt similarity",
                    }
                )
            if frame.get("mini_world") == previous.get("mini_world"):
                mini_world_streak += 1
            else:
                mini_world_streak = 1
            if normalize_text_lower(frame.get("main_subject", "")) == normalize_text_lower(previous.get("main_subject", "")):
                subject_streak += 1
            else:
                subject_streak = 1
        else:
            mini_world_streak = 1
            subject_streak = 1

        if mini_world_streak >= 4:
            flags.add("mini_world_streak")
        if subject_streak >= 5:
            flags.add("main_subject_streak")

        if frame.get("dc_status") == "rewrite":
            flags.add("directors_cut_rewrite")
        frame["qc_flags"] = sorted(flags)
        if frame["qc_flags"]:
            rewrite_items.append(
                {
                    "frame_id": frame["frame_id"],
                    "scene_id": frame["scene_id"],
                    "problem": ", ".join(frame["qc_flags"]),
                    "instruction": "Change mini-world or subject emphasis while preserving ID and timing.",
                }
            )
            weak_rows.append({"frame_id": frame["frame_id"], "issues": "; ".join(frame["qc_flags"])})
        previous = frame

    repeated_families = sum(1 for count in family_counts.values() if count >= 3)
    pattern_breaks = count_pattern_breaks(frames, seconds_window=30.0)
    report_lines.extend(
        [
            f"Frames checked: {len(frames)}",
            f"Rewrite targets: {len(rewrite_items)}",
            f"Repeated prompt families: {repeated_families}",
            f"Pattern breaks within 30s windows: {pattern_breaks}",
        ]
    )

    _save_storyboard_frames(project, frames)
    save_json(Path(project["prompts"]["rewrite_queue_path"]), {"project_id": project["project_id"], "frames_to_rewrite": rewrite_items})
    Path(project["reports"]["qc_report_md_path"]).write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    write_csv(Path(project["reports"]["duplicate_report_csv_path"]), duplicate_rows or [{"frame_id": "", "other_frame_id": "", "similarity": "", "reason": ""}])
    write_csv(Path(project["reports"]["weak_frames_csv_path"]), weak_rows or [{"frame_id": "", "issues": ""}])
    save_json(
        Path(project["logs"]["qa_report_json_path"]),
        {
            "project_id": project["project_id"],
            "status": "failed" if rewrite_items else "passed",
            "errors": [item["problem"] for item in rewrite_items],
            "warnings": [f"repeated_prompt_families:{repeated_families}"] if repeated_families else [],
            "stage_results": [{"stage": "qc", "status": "failed" if rewrite_items else "passed"}],
        },
    )
    project["qc"]["status"] = "failed" if rewrite_items else "passed"
    project["qc"]["last_result"] = {"rewrite_count": len(rewrite_items)}
    project["current_stage"] = "rewrite_flagged" if rewrite_items else "export_generator_queue"
    save_project(project_json, project)
    return Path(project["prompts"]["rewrite_queue_path"])


def rewrite_v2_flagged(project_json: Path) -> Path:
    project_json = Path(project_json).resolve()
    project = load_project(project_json)
    rewrite_queue = load_json(Path(project["prompts"]["rewrite_queue_path"]))
    rewrite_lookup = {item["frame_id"]: item for item in rewrite_queue.get("frames_to_rewrite", [])}
    frames = _load_storyboard_frames(project)
    for frame in frames:
        instruction = rewrite_lookup.get(frame["frame_id"])
        if not instruction:
            continue
        frame["mini_world"] = f"{frame['mini_world']} / revised"
        frame["why_this_frame_exists"] = normalize_text(
            f"{frame['why_this_frame_exists']} Revised after QC to add a clearer visual distinction."
        )
        frame["image_prompt_final"] = _rebuild_prompt(frame, variant_note="Emphasize a fresh investigative angle.")
        frame["dc_status"] = "revised"
        frame["qc_flags"] = [flag for flag in frame.get("qc_flags", []) if flag not in {"possible_duplicate_prompt", "directors_cut_rewrite"}]
    _save_storyboard_frames(project, frames)
    project["prompts"]["status"] = "v2_rewrites_applied"
    project["current_stage"] = "export_generator_queue"
    save_project(project_json, project)
    return Path(project["planning"]["storyboard_frames_path"])


def export_v2_generator_queue(project_json: Path) -> Path:
    project_json = Path(project_json).resolve()
    project = load_project(project_json)
    frames = _load_storyboard_frames(project)
    rows = []
    for frame in frames:
        rows.append(
            {
                "frame_id": frame["frame_id"],
                "scene_id": frame["scene_id"],
                "subscene_id": frame["subscene_id"],
                "start_time": frame["start_time"],
                "end_time": frame["end_time"],
                "duration_sec": frame["duration_sec"],
                "image_prompt_final": frame["image_prompt_final"],
                "negative_prompt": frame["negative_prompt"],
                "motion_plan": "slow push-in" if frame["visual_function"] != "pattern_break" else "hard cut",
                "image_filename": f"{frame['frame_id']}.png",
            }
        )
    path = Path(project["exports"]["generator_queue_csv_path"])
    write_csv(path, rows)
    project["current_stage"] = "export_edit_timeline"
    save_project(project_json, project)
    return path


def export_v2_edit_timeline(project_json: Path) -> Path:
    project_json = Path(project_json).resolve()
    project = load_project(project_json)
    frames = _load_storyboard_frames(project)
    timeline_rows = []
    srt_blocks = []
    for index, frame in enumerate(frames, start=1):
        timeline_rows.append(
            {
                "frame_id": frame["frame_id"],
                "scene_id": frame["scene_id"],
                "start_time": frame["start_time"],
                "end_time": frame["end_time"],
                "duration_sec": frame["duration_sec"],
                "mini_world": frame["mini_world"],
                "main_subject": frame["main_subject"],
                "editorial_note": frame["why_this_frame_exists"],
            }
        )
        start_seconds = _parse_dot_timestamp(frame["start_time"])
        end_seconds = _parse_dot_timestamp(frame["end_time"])
        srt_blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{format_srt_timestamp(start_seconds)} --> {format_srt_timestamp(end_seconds)}",
                    normalize_text(frame["why_this_frame_exists"]),
                ]
            )
        )
    write_csv(Path(project["exports"]["edit_timeline_csv_path"]), timeline_rows)
    Path(project["exports"]["frame_timing_srt_path"]).write_text("\n\n".join(srt_blocks) + "\n", encoding="utf-8")
    Path(project["exports"]["thumbnails_json_path"]).write_text(
        json.dumps(
            {
                "project_id": project["project_id"],
                "candidates": [
                    {
                        "frame_id": frame["frame_id"],
                        "prompt": frame["image_prompt_final"],
                        "reason": frame["why_this_frame_exists"],
                    }
                    for frame in frames[: min(6, len(frames))]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    save_project(project_json, project)
    return Path(project["exports"]["edit_timeline_csv_path"])


def make_v2_test_batch(project_json: Path, count: int = 30) -> Path:
    project_json = Path(project_json).resolve()
    project = load_project(project_json)
    generator_queue_path = Path(project["exports"]["generator_queue_csv_path"])
    if not generator_queue_path.exists():
        raise FileNotFoundError("generator_queue.csv not found; run export-generator-queue first")
    rows = generator_queue_path.read_text(encoding="utf-8").splitlines()
    batch_path = generator_queue_path.with_name(f"test_batch_{count}.csv")
    batch_path.write_text("\n".join(rows[: count + 1]) + "\n", encoding="utf-8")
    return batch_path


def _parse_dot_timestamp(value: str) -> float:
    hh, mm, rest = value.split(":")
    ss, ms = rest.split(".")
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0
