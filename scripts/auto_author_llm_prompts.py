import argparse
import re
from pathlib import Path

from project_pipeline_utils import load_json, load_project, save_json, save_project
from llm_pipeline_contracts import validate_scene_prompt_drafts_payload, validate_visual_bible_payload
from yt_nonstop.providers.llm_provider import LLMProvider, LLMRequest, build_json_only_prompt, provider_from_project


STYLE_SUMMARY = (
    "Premium cinematic documentary still, photorealistic, realistic lens perspective, atmospheric depth, "
    "natural imperfections, 16:9 composition, no text."
)


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("\n", " ")).strip()


def summarize_phrase(text: str, limit: int = 140) -> str:
    text = clean_text(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def looks_noisy(text: str) -> bool:
    text = clean_text(text)
    if not text:
        return True
    mojibake_markers = ("РџС", "РљР", "СЃ", "Рё", "В«", "В»", "вЂ”", "вЂ¦")
    if any(marker in text for marker in mojibake_markers):
        return True
    meaningful_letters = re.findall(r"[A-Za-zÀ-ÿА-Яа-я]", text)
    if not meaningful_letters:
        return True
    return len(meaningful_letters) / max(len(text), 1) < 0.25


def infer_theme(records: list[dict], project: dict) -> str:
    title = clean_text(project.get("meta", {}).get("title", "")).lower()
    project_id = clean_text(project.get("project_id", "")).lower()
    joined = " ".join(clean_text(item.get("voice_text", "")) for item in records).lower()
    blob = f"{title} {project_id} {joined}"
    if any(marker in blob for marker in {"pantery", "panther", "jewel", "jewelry", "diamond", "boutique", "heist", "robbery"}):
        return "luxury_jewel_heist_documentary"
    if any(marker in blob for marker in {"wolf", "wolves", "wildlife", "yellowstone"}):
        return "wildlife_documentary"
    return "generic_documentary"


def profile_lookup(record: dict) -> dict[str, dict]:
    entities = {}
    for bucket in (
        record.get("active_character_profiles", []),
        record.get("active_object_profiles", []),
        record.get("active_location_profiles", []),
    ):
        for entity in bucket:
            entity_id = str(entity.get("entity_id", "")).strip()
            if entity_id:
                entities[entity_id] = entity
    return entities


def infer_shot_role(record: dict, theme: str) -> str:
    active = set(record.get("active_entity_ids", []))
    shot_index = int(record.get("shot_index") or 0)
    voice_text = clean_text(record.get("voice_text", "")).lower()
    if record.get("event_type") == "assault_moment":
        return "assault_moment"
    if record.get("event_type") == "theft_reveal":
        return "empty_case_reveal"
    if record.get("event_type") == "entry_moment":
        return "operator_entry"
    if record.get("event_type") == "access_moment":
        return "necklace_access"
    if theme == "luxury_jewel_heist_documentary":
        if any(marker in voice_text for marker in {"ослеп", "газ", "blinded", "blinding", "irritant gas", "spray"}):
            return "assault_moment"
        if any(marker in voice_text for marker in {"витрина открыта", "исчезает", "open case", "empty case", "jewel disappears", "missing jewel"}):
            return "empty_case_reveal"
        if "lead_operator" in active and "support_operator" in active and shot_index <= 8:
            return "operator_entry"
        if "signature_necklace" in active and "boutique_attendant" in active:
            return "necklace_access"
        if "security_guard" in active:
            return "security_system"
        if "signature_necklace" in active and shot_index <= 4:
            return "luxury_establishing"
        if shot_index >= 15:
            return "aftermath_escape"
        return "investigative_bridge"
    return "documentary_bridge"


def scene_blueprint(record: dict, theme: str) -> dict:
    shot_role = infer_shot_role(record, theme)
    shot_index = int(record.get("shot_index") or 0)

    if theme == "luxury_jewel_heist_documentary":
        mapping = {
            "luxury_establishing": {
                "scene_meaning": "Establish the boutique as a meticulously protected luxury environment with value and tension already baked into the space.",
                "visual_function": "hook" if shot_index <= 2 else "evidence",
                "visual_strategy": "mechanism_view",
                "viewer_emotion": "curiosity, tension, controlled awe",
                "narrative_purpose": "hook",
                "visual_idea": "Show the boutique as a machine of luxury security rather than a simple store interior.",
                "camera": "wide architectural documentary angle" if shot_index == 1 else "top-down surveillance angle",
                "composition": "layered foreground reflections, controlled symmetry, hero object protected inside the frame",
                "lighting": "restrained warm luxury lighting mixed with colder security highlights",
                "mood": "tense, premium, investigative",
                "scene_importance": "key",
            },
            "security_system": {
                "scene_meaning": "Reveal the hidden system that watches the room and controls access.",
                "visual_function": "evidence",
                "visual_strategy": "mechanism_view",
                "viewer_emotion": "pressure, scrutiny",
                "narrative_purpose": "explain",
                "visual_idea": "Translate security logic into a visual network of cameras, locks, and guard presence.",
                "camera": "over-the-shoulder documentary angle",
                "composition": "foreground hardware detail with guard or reflected boutique depth behind it",
                "lighting": "cool security spill with warm boutique accents",
                "mood": "controlled, watchful, procedural",
                "scene_importance": "supporting",
            },
            "operator_entry": {
                "scene_meaning": "Introduce the same two operators as composed affluent customers who do not belong emotionally to the room.",
                "visual_function": "pattern_break",
                "visual_strategy": "human_consequence",
                "viewer_emotion": "unease, suspicion",
                "narrative_purpose": "turning_point",
                "visual_idea": "Show the pair entering the controlled boutique world while still blending in.",
                "camera": "medium documentary angle at eye level" if shot_index <= 6 else "low three-quarter angle",
                "composition": "one operator leading, the other slightly behind, with display glass and cameras framing them",
                "lighting": "motivated boutique light with subtle cold reflections on glass",
                "mood": "quietly threatening, controlled, elegant",
                "scene_importance": "key",
            },
            "necklace_access": {
                "scene_meaning": "Show the exact moment the attendant opens controlled access to the necklace display.",
                "visual_function": "explain",
                "visual_strategy": "evidence_wall",
                "viewer_emotion": "anticipation, precision",
                "narrative_purpose": "explain",
                "visual_idea": "Show the attendant actively opening the protected case while the necklace, lock hardware, and observing operator remain readable in the same frame, without becoming tutorial-like.",
                "camera": "close documentary angle" if shot_index < 11 else "macro evidence angle",
                "composition": "the opening gesture and access hardware are instantly readable, with the necklace and partial human presence anchored in the same controlled frame",
                "lighting": "tight gallery spotlight with soft edge reflections",
                "mood": "precise, tense, forensic",
                "scene_importance": "key",
            },
            "aftermath_escape": {
                "scene_meaning": "Show disruption, absence, and the speed of the aftermath without glamorizing the operators.",
                "visual_function": "payoff" if shot_index >= 18 else "contrast",
                "visual_strategy": "human_consequence",
                "viewer_emotion": "shock, confusion, cold realization",
                "narrative_purpose": "payoff",
                "visual_idea": "Turn the missing jewel and delayed human reaction into the emotional closing image.",
                "camera": "handheld-feeling documentary angle" if shot_index < 18 else "wide exit-facing angle",
                "composition": "empty case, partial figures, and directional movement toward absence",
                "lighting": "luxury lighting disrupted by harsher practical spill",
                "mood": "disoriented, urgent, investigative",
                "scene_importance": "key",
            },
            "assault_moment": {
                "scene_meaning": "Show the exact instant the boutique attendant is hit by the blinding irritant, with the action readable in one frame.",
                "visual_function": "emotion",
                "visual_strategy": "tension_detail",
                "viewer_emotion": "shock, urgency, disorientation",
                "narrative_purpose": "turning_point",
                "visual_idea": "Show the attendant recoiling as the irritant mist hits, with the support operator partially visible and the protected display case still in frame.",
                "camera": "tight over-the-shoulder action angle",
                "composition": "the attendant's recoil and the burst of irritant are instantly readable, with the case and operator placement anchoring the geography",
                "lighting": "luxury interior light fractured by harsh specular reflections and sudden motion",
                "mood": "violent, immediate, documentary-real",
                "scene_importance": "key",
            },
            "empty_case_reveal": {
                "scene_meaning": "Show the open case and the immediate realization that the jewel is gone.",
                "visual_function": "payoff",
                "visual_strategy": "contrast",
                "viewer_emotion": "shock, disbelief",
                "narrative_purpose": "payoff",
                "visual_idea": "Show the now-open display case with the necklace missing, while hands, reflections, or blurred staff movement convey immediate chaos.",
                "camera": "close forensic documentary angle",
                "composition": "the empty pedestal dominates the frame while partial figures and reflections deliver the emotional fallout",
                "lighting": "tight gallery light on the empty mount with colder spill in the background",
                "mood": "forensic, stunned, urgent",
                "scene_importance": "key",
            },
            "investigative_bridge": {
                "scene_meaning": "Carry the story forward with one coherent investigative image rooted in the same boutique world.",
                "visual_function": "transition",
                "visual_strategy": "scale_contrast",
                "viewer_emotion": "attention, narrative pull",
                "narrative_purpose": "transition",
                "visual_idea": "Bridge adjacent beats through the same cast, same object world, and a fresh camera position.",
                "camera": "medium documentary angle",
                "composition": "repeat recurring entities but vary scale, depth, and direction of sightlines",
                "lighting": "motivated interior lighting with reflective depth",
                "mood": "coherent, restrained, cinematic",
                "scene_importance": "supporting",
            },
        }
        return mapping[shot_role]

    if theme == "wildlife_documentary":
        return {
            "scene_meaning": "Keep the same animal group and habitat coherent across the sequence.",
            "visual_function": "transition",
            "visual_strategy": "literal_premium",
            "viewer_emotion": "attention, stillness",
            "narrative_purpose": "transition",
            "visual_idea": "Use one consistent wildlife world rather than random animal imagery.",
            "camera": "telephoto wildlife documentary angle",
            "composition": "clear subject separation inside a believable ecosystem",
            "lighting": "natural cold daylight or low sun depending on scene",
            "mood": "observational, restrained, coherent",
            "scene_importance": "supporting",
        }

    return {
        "scene_meaning": "Translate the narration into one coherent documentary shot inside a recurring visual world.",
        "visual_function": "transition",
        "visual_strategy": "literal_premium",
        "viewer_emotion": "interest, clarity",
        "narrative_purpose": "transition",
        "visual_idea": "Use recurring people and props instead of random replacements.",
        "camera": "medium documentary angle",
        "composition": "one recurring subject framed with readable depth and grounded context",
        "lighting": "motivated practical lighting",
        "mood": "coherent, grounded, cinematic",
        "scene_importance": "supporting",
    }


def build_subject_lines(record: dict, entities: dict[str, dict], theme: str) -> tuple[str, list[str], list[str]]:
    active_entity_ids = list(dict.fromkeys(record.get("active_entity_ids", [])))
    active_profiles = [entities[entity_id]["profile"] for entity_id in active_entity_ids if entity_id in entities]
    profile_lines = [f"{entity_id}: {entities[entity_id]['profile']}" for entity_id in active_entity_ids if entity_id in entities]
    shot_role = infer_shot_role(record, theme)

    if theme == "luxury_jewel_heist_documentary":
        if shot_role == "security_system":
            primary_subject = "the boutique security layer controlling access to the room"
        elif shot_role == "assault_moment":
            primary_subject = "the boutique attendant being blinded in the instant of the attack"
        elif shot_role == "empty_case_reveal":
            primary_subject = "the same display case now open with the necklace suddenly missing"
        elif shot_role == "necklace_access":
            primary_subject = "the attendant opening controlled access to the signature necklace display"
        elif shot_role == "operator_entry":
            primary_subject = "the same two operators moving through the boutique under surveillance"
        elif shot_role == "aftermath_escape":
            primary_subject = "the same two operators leaving behind a sudden absence in the boutique"
        elif "signature_necklace" in active_entity_ids:
            primary_subject = "the same signature necklace inside the protected display case"
        else:
            primary_subject = "the same luxury-security boutique environment"
    elif theme == "wildlife_documentary":
        primary_subject = "the same recurring animal group inside the same ecosystem"
    else:
        primary_subject = "the same recurring documentary subject inside one coherent environment"

    return primary_subject, active_profiles, profile_lines


def build_visual_description(record: dict, blueprint: dict, primary_subject: str) -> str:
    continuity_focus = clean_text(record.get("continuity_focus", ""))
    base = (
        f"Show {primary_subject} in a way that reflects {blueprint['scene_meaning'].lower()} "
        f"and feels like one unified documentary film rather than a random standalone image."
    )
    if record.get("event_clarity_required"):
        base += " The frame must make the narrated event readable within one second."
    if continuity_focus:
        base += f" Keep the frame focused on {continuity_focus}."
    return base


def build_prompt(record: dict, theme: str, visual_bible: dict) -> dict:
    blueprint = scene_blueprint(record, theme)
    entities = profile_lookup(record)
    primary_subject, _, profile_lines = build_subject_lines(record, entities, theme)
    voice_text = clean_text(record.get("voice_text", ""))
    voice_summary = "narration fragment unavailable or noisy" if looks_noisy(voice_text) else summarize_phrase(voice_text, 140)
    atmosphere = blueprint["mood"]
    angle = blueprint["camera"]
    lighting = blueprint["lighting"]
    style_summary = record.get("style_summary") or visual_bible.get("style_summary") or STYLE_SUMMARY
    continuity_world = clean_text(record.get("continuity_world", "")) or clean_text(visual_bible.get("visual_world", ""))
    continuity_mode = clean_text(record.get("continuity_mode", "")) or "fallback"
    recurring_motifs = ", ".join(record.get("recurring_motifs", [])[:4])
    location_profiles = [item["profile"] for item in record.get("active_location_profiles", []) if item.get("profile")]
    object_profiles = [item["profile"] for item in record.get("active_object_profiles", []) if item.get("profile")]
    environment = location_profiles[0] if location_profiles else "a grounded documentary environment connected to the narration"

    details = []
    if object_profiles:
        details.append(object_profiles[0])
    if recurring_motifs:
        details.append(f"Recurring motifs: {recurring_motifs}")
    if "lead_operator" in record.get("active_entity_ids", []):
        details.append("Keep the lead operator visually identical to his earlier appearance in suit, posture, and grooming.")
    if "support_operator" in record.get("active_entity_ids", []):
        details.append("Keep the support operator visually identical to her earlier appearance in coat, hairstyle, and silhouette.")
    if "boutique_attendant" in record.get("active_entity_ids", []):
        details.append("Keep the boutique attendant visually identical in uniform, bun hairstyle, and professional posture.")
    if "security_guard" in record.get("active_entity_ids", []):
        details.append("Keep the security guard visually identical with shaved head, navy suit, and earpiece.")
    continuity_lines = [f"- {line}" for line in profile_lines] or ["- Reuse the same recurring subject design across the sequence."]
    detail_lines = [f"- {detail}" for detail in details] or ["- Maintain realistic physical detail and layered depth."]

    prompt_lines = [
        "Create a premium cinematic documentary still in 16:9.",
        "",
        f"Scene meaning: {blueprint['scene_meaning']}",
        f"Visual: {build_visual_description(record, blueprint, primary_subject)}",
        f"Main subject: {primary_subject}",
        "Character continuity:",
    ]
    prompt_lines.extend(continuity_lines)
    prompt_lines.extend(
        [
            f"Action without speech: {blueprint['visual_idea']}",
            f"Environment: {environment}",
            f"Composition: {blueprint['composition']}",
            f"Angle: {angle}",
            "Camera: realistic documentary photography, natural lens perspective, cinematic framing, realistic depth of field",
            f"Lighting: {lighting}",
            f"Atmosphere: {atmosphere}",
            "Important details:",
        ]
    )
    prompt_lines.extend(detail_lines)
    prompt_lines.extend(
        [
            f"Style: {style_summary}",
            "Restrictions: no real-person names, no text, no subtitles, no logos, no watermark, no fake UI, no distorted hands, no plastic skin, no glamorized crime framing, no random replacement characters",
        ]
    )
    final_prompt = "\n".join(prompt_lines)

    return {
        "scene_id": record["scene_id"],
        "frame_id": record.get("frame_id") or record["scene_id"].replace("scene_", "F"),
        "beat_id": record.get("beat_id") or record["scene_id"].replace("scene_", "beat_"),
        "shot_id": record.get("shot_id"),
        "source_shot_id": record.get("source_shot_id"),
        "generation_mode": record.get("generation_mode", "unique"),
        "shot_type": record.get("shot_type", infer_shot_role(record, theme)),
        "film_block_id": record.get("film_block_id", ""),
        "transition_in": record.get("transition_in", "cut"),
        "transition_out": record.get("transition_out", "cut_on_phrase_end"),
        "scene_meaning": blueprint["scene_meaning"],
        "narrative_purpose": blueprint["narrative_purpose"],
        "viewer_emotion": blueprint["viewer_emotion"],
        "visual_function": blueprint["visual_function"],
        "visual_strategy": blueprint["visual_strategy"],
        "visual_idea": blueprint["visual_idea"],
        "main_subject": primary_subject,
        "environment": environment,
        "visual_goal": blueprint["scene_meaning"],
        "visualized_claim": record.get("spoken_claim") or blueprint["scene_meaning"],
        "must_show": list(record.get("must_show") or record.get("must_visualize", [])),
        "scene_importance": blueprint["scene_importance"],
        "beat_priority": record.get("beat_priority", "supporting"),
        "key_beat": bool(record.get("key_beat")),
        "variant_count": int(record.get("variant_count", 1) or 1),
        "shot_role": infer_shot_role(record, theme),
        "primary_subject": primary_subject,
        "secondary_subjects": [],
        "what_is_in_frame": build_visual_description(record, blueprint, primary_subject),
        "camera": angle,
        "composition": blueprint["composition"],
        "lighting": lighting,
        "mood": atmosphere,
        "continuity_notes": (
            f"Continuity world: {continuity_world}. "
            "Use the same recurring entity descriptions verbatim whenever those entities appear again. "
            + ("Continuity map missing, so preserve the same world through repeated wardrobe, silhouette, and object identity cues. " if continuity_mode == "fallback" else "")
            + (str(record.get("event_priority_reason", "")).strip() if record.get("event_clarity_required") else "")
        ).strip(),
        "must_not_show": [
            "different face for recurring character",
            "new outfit without a wardrobe change event",
            "readable text or subtitles",
            "fake UI",
        ],
        "negative_prompt": "text, subtitle, logo, watermark, fake UI, unreadable signage, glamorized criminal hero shot, random replacement character, distorted hands, plastic skin",
        "draft_prompt": final_prompt,
        "final_prompt": final_prompt,
        "active_entity_ids": list(record.get("active_entity_ids", [])),
        "continuity_cast": profile_lines,
        "reference_ids": list(record.get("reference_ids", [])),
        "continuity_mode": continuity_mode,
        "voiceover_summary": voice_summary,
        "event_clarity_required": bool(record.get("event_clarity_required")),
        "event_type": str(record.get("event_type", "")),
        "event_priority_reason": str(record.get("event_priority_reason", "")),
    }


def build_visual_bible(project: dict, records: list[dict]) -> dict:
    theme = infer_theme(records, project)
    if theme == "luxury_jewel_heist_documentary":
        subject = "an investigative documentary about a luxury jewel heist inside a tightly controlled boutique"
        motifs = ["glass reflections", "surveillance cameras", "display-case hardware", "forensic luxury detail"]
    elif theme == "wildlife_documentary":
        subject = "a wildlife documentary with one recurring animal group and one coherent ecosystem"
        motifs = ["distance compression", "weathered terrain", "watchful stillness", "natural hierarchy"]
    else:
        subject = "a premium documentary narrative with recurring people, locations, and key objects"
        motifs = ["foreground/background storytelling", "documentary evidence", "controlled realism"]

    return {
        "project_id": project["project_id"],
        "contract_type": "visual_bible.v1",
        "main_subject": subject,
        "subject_type": theme,
        "visual_world": (
            f"{subject}. Keep the same people, objects, and locations visually stable whenever they recur. "
            "Prompts must remain in English, documentary-safe, and grounded in one coherent film language."
        ),
        "style_summary": STYLE_SUMMARY,
        "prompt_language": "English",
        "recurring_motifs": motifs,
        "continuity_rules": [
            "Repeat the same character and object descriptions verbatim whenever those entities return.",
            "Do not introduce random new faces if a recurring role already exists.",
            "Every prompt must include style, atmosphere, lighting, and angle.",
            "No visible text, logos, watermarks, or real-person names.",
        ],
        "forbidden_mistakes": [
            "Replacing recurring characters with random strangers",
            "Literal stock-photo illustration with no atmosphere",
            "Text or labels inside the image",
            "Glamorized crime imagery or tutorial framing",
        ],
        "scene_role_taxonomy": [
            "luxury_establishing",
            "security_system",
            "operator_entry",
            "necklace_access",
            "assault_moment",
            "empty_case_reveal",
            "aftermath_escape",
            "investigative_bridge",
            "documentary_bridge",
        ],
        "visual_blocks": [],
        "global_negative_prompt": [
            "text",
            "subtitle",
            "watermark",
            "logo",
            "cartoon",
            "random replacement character",
            "glamorized crime hero shot",
            "unreadable gibberish text",
        ],
    }


def compact_text(value: object, limit: int = 600) -> str:
    text = clean_text(value if isinstance(value, str) else "")
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def coerce_visual_bible(project: dict, records: list[dict], payload: object) -> dict:
    fallback = build_visual_bible(project, records)
    if not isinstance(payload, dict):
        return fallback

    creative_intent = payload.get("creative_intent", {}) if isinstance(payload.get("creative_intent"), dict) else {}
    visual_world = payload.get("visual_world", {}) if isinstance(payload.get("visual_world"), dict) else {}
    motifs = payload.get("recurring_motifs")
    if not isinstance(motifs, list) or not motifs:
        motifs = (
            visual_world.get("world_metaphors")
            or payload.get("sound_implied_visuals", {}).get("rhythm_keywords")
            or fallback["recurring_motifs"]
        )
    continuity_rules = payload.get("continuity_rules")
    if not isinstance(continuity_rules, list) or not continuity_rules:
        continuity_rules = fallback["continuity_rules"]

    main_subject = (
        compact_text(payload.get("main_subject"))
        or compact_text(creative_intent.get("logline"))
        or compact_text(fallback["main_subject"])
    )
    visual_world_summary = compact_text(payload.get("visual_world"))
    if not visual_world_summary:
        visual_world_summary = compact_text(creative_intent.get("core_theme"))
    if not visual_world_summary:
        visual_world_summary = fallback["visual_world"]

    coerced = dict(fallback)
    coerced.update(
        {
            "project_id": payload.get("project_id") or fallback["project_id"],
            "main_subject": main_subject,
            "subject_type": payload.get("subject_type") or fallback["subject_type"],
            "visual_world": visual_world_summary,
            "style_summary": compact_text(payload.get("style_summary")) or fallback["style_summary"],
            "prompt_language": payload.get("prompt_language") or "English",
            "recurring_motifs": motifs if isinstance(motifs, list) else fallback["recurring_motifs"],
            "continuity_rules": continuity_rules,
            "forbidden_mistakes": payload.get("forbidden_mistakes") if isinstance(payload.get("forbidden_mistakes"), list) else fallback["forbidden_mistakes"],
            "scene_role_taxonomy": payload.get("scene_role_taxonomy") if isinstance(payload.get("scene_role_taxonomy"), list) else fallback["scene_role_taxonomy"],
            "visual_blocks": payload.get("visual_blocks") if isinstance(payload.get("visual_blocks"), list) else fallback["visual_blocks"],
            "global_negative_prompt": payload.get("global_negative_prompt") if isinstance(payload.get("global_negative_prompt"), list) else fallback["global_negative_prompt"],
        }
    )
    return coerced


def build_visual_bible_context(project: dict, records: list[dict]) -> dict:
    compact_records = []
    for record in records:
        compact_records.append(
            {
                "scene_id": record.get("scene_id"),
                "beat_id": record.get("beat_id"),
                "voice_text": record.get("voice_text"),
                "spoken_claim": record.get("spoken_claim"),
                "must_show": record.get("must_show"),
                "active_entity_ids": record.get("active_entity_ids", []),
                "continuity_cast": record.get("continuity_cast", []),
                "environment": record.get("environment"),
                "film_block_id": record.get("film_block_id"),
            }
        )
    return {
        "task": "author_visual_bible",
        "project_id": project.get("project_id"),
        "language": project.get("meta", {}).get("language"),
        "scene_records": compact_records,
        "requirements": [
            "Return a JSON object only.",
            "Define a coherent visual world for the full film.",
            "Do not include file paths, runtime statuses, or technical state.",
        ],
    }


def build_prompt_authoring_context(project: dict, records: list[dict], visual_bible: dict) -> dict:
    compact_records = []
    for record in records:
        compact_records.append(
            {
                "scene_id": record.get("scene_id"),
                "frame_id": record.get("frame_id"),
                "beat_id": record.get("beat_id"),
                "shot_id": record.get("shot_id"),
                "film_block_id": record.get("film_block_id"),
                "voice_text": record.get("voice_text"),
                "spoken_claim": record.get("spoken_claim"),
                "must_show": record.get("must_show"),
                "camera": record.get("camera"),
                "composition": record.get("composition"),
                "lighting": record.get("lighting"),
                "mood": record.get("mood"),
                "active_entity_ids": record.get("active_entity_ids", []),
                "reference_ids": record.get("reference_ids", []),
                "event_clarity_required": bool(record.get("event_clarity_required")),
            }
        )
    return {
        "task": "author_scene_prompt_drafts",
        "project_id": project.get("project_id"),
        "language": project.get("meta", {}).get("language"),
        "visual_bible": {
            "project_id": visual_bible.get("project_id"),
            "main_subject": visual_bible.get("main_subject"),
            "subject_type": visual_bible.get("subject_type"),
            "visual_world": visual_bible.get("visual_world"),
            "style_summary": visual_bible.get("style_summary"),
            "prompt_language": visual_bible.get("prompt_language"),
            "recurring_motifs": visual_bible.get("recurring_motifs", []),
            "continuity_rules": visual_bible.get("continuity_rules", []),
            "global_negative_prompt": visual_bible.get("global_negative_prompt", []),
        },
        "scene_records": compact_records,
        "requirements": [
            "Return JSON only.",
            "Return an array of scene prompt draft objects.",
            "Each record must include scene_id, visual_goal, and final_prompt.",
            "Do not include file paths, statuses, or runtime fields.",
        ],
    }


def pilot_authoring_records(project: dict, records: list[dict]) -> list[dict]:
    limit = int(project.get("runtime", {}).get("limit_frames", 0) or 0)
    if limit <= 0:
        return records
    return records[:limit]


def sampled_visual_bible_records(records: list[dict], sample_size: int = 8) -> list[dict]:
    if len(records) <= sample_size:
        return records
    last_index = len(records) - 1
    chosen_indices = {0, last_index}
    for step in range(1, sample_size - 1):
        chosen_indices.add(round((last_index * step) / (sample_size - 1)))
    return [records[index] for index in sorted(chosen_indices)]


def batched_records(records: list[dict], batch_size: int = 10) -> list[list[dict]]:
    size = max(1, int(batch_size or 1))
    return [records[index : index + size] for index in range(0, len(records), size)]


def coerce_prompt_drafts(batch: list[dict], drafts_payload: object) -> list[dict]:
    if not isinstance(drafts_payload, list):
        return []
    batch_by_scene = {
        str(record.get("scene_id", "")).strip(): record
        for record in batch
        if str(record.get("scene_id", "")).strip()
    }
    coerced: list[dict] = []
    for record in drafts_payload:
        if not isinstance(record, dict):
            continue
        scene_id = str(record.get("scene_id", "")).strip()
        source = batch_by_scene.get(scene_id, {})
        merged = dict(record)
        merged.setdefault("frame_id", source.get("frame_id"))
        merged.setdefault("beat_id", source.get("beat_id"))
        merged.setdefault("visualized_claim", source.get("spoken_claim") or source.get("voice_text") or merged.get("visual_goal", ""))
        merged.setdefault("must_show", source.get("must_show", []))
        coerced.append(merged)
    return coerced


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--provider", default="", help="LLM provider mode override: file, command, http, openai_compatible, disabled.")
    parser.add_argument("--input-json", help="Optional file-mode JSON payload containing visual_bible and llm_prompt_drafts.")
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    context_path = Path(project["prompts"]["scene_context_pack_path"])
    visual_bible_path = Path(project["prompts"]["visual_bible_path"])
    drafts_path = Path(project["prompts"]["llm_prompt_drafts_path"])

    records = load_json(context_path)
    authoring_records = pilot_authoring_records(project, records)
    provider_config = provider_from_project(
        project,
        stage_name="auto_author_llm_prompts",
        override_mode=args.provider or None,
        input_json_path=str(Path(args.input_json).resolve()) if args.input_json else None,
    )
    if provider_config.mode == "disabled":
        visual_bible = build_visual_bible(project, authoring_records)
        theme = visual_bible["subject_type"]
        subset_drafts = [build_prompt(record, theme, visual_bible) for record in authoring_records]
    else:
        provider = LLMProvider(provider_config)
        vb_context = build_visual_bible_context(project, sampled_visual_bible_records(authoring_records))
        vb_response = provider.invoke(
            LLMRequest(
                stage_name="auto_author_llm_prompts",
                task="author_visual_bible",
                contract_name="visual_bible.v1",
                system_prompt="You are a visual bible author for a narrated silent-image film pipeline. Return JSON only.",
                user_prompt=build_json_only_prompt(
                    instruction="Author the project visual bible from this context.",
                    context=vb_context,
                ),
                context=vb_context,
                response_key="visual_bible",
            )
        )
        if provider_config.mode == "file" and isinstance(vb_response.payload, dict) and "visual_bible" in vb_response.payload:
            visual_bible = vb_response.payload["visual_bible"]
        else:
            visual_bible = vb_response.payload
        visual_bible = coerce_visual_bible(project, authoring_records, visual_bible)
        vb_errors, _ = validate_visual_bible_payload(visual_bible)
        if vb_errors:
            raise RuntimeError("Invalid visual_bible from provider:\n" + "\n".join(vb_errors))
        subset_drafts = []
        for batch in batched_records(authoring_records, batch_size=3):
            prompt_context = build_prompt_authoring_context(project, batch, visual_bible)
            prompt_response = provider.invoke(
                LLMRequest(
                    stage_name="auto_author_llm_prompts",
                    task="author_scene_prompt_drafts",
                    contract_name="llm_prompt_drafts.v1",
                    system_prompt="You are a prompt author for a narrated silent-image film pipeline. Return JSON only.",
                    user_prompt=build_json_only_prompt(
                        instruction="Author the scene prompt drafts from this context.",
                        context=prompt_context,
                    ),
                    context=prompt_context,
                    response_key="llm_prompt_drafts",
                )
            )
            if provider_config.mode == "file" and isinstance(prompt_response.payload, dict):
                drafts_payload = prompt_response.payload.get("llm_prompt_drafts") or prompt_response.payload.get("drafts") or prompt_response.payload
            elif isinstance(prompt_response.payload, dict):
                drafts_payload = prompt_response.payload.get("llm_prompt_drafts") or prompt_response.payload.get("drafts") or prompt_response.payload
            else:
                drafts_payload = prompt_response.payload
            batch_drafts = coerce_prompt_drafts(batch, drafts_payload)
            expected_scene_ids = [str(record.get("scene_id")) for record in batch if record.get("scene_id")]
            draft_errors, _ = validate_scene_prompt_drafts_payload(batch_drafts, expected_scene_ids=expected_scene_ids)
            if draft_errors:
                raise RuntimeError("Invalid llm_prompt_drafts from provider:\n" + "\n".join(draft_errors))
            subset_drafts.extend(batch_drafts)

    existing_drafts = load_json(drafts_path) if drafts_path.exists() else []
    drafts_by_scene = {
        str(record.get("scene_id", "")).strip(): record
        for record in existing_drafts
        if isinstance(record, dict) and str(record.get("scene_id", "")).strip()
    }
    for record in subset_drafts:
        scene_id = str(record.get("scene_id", "")).strip()
        if scene_id:
            drafts_by_scene[scene_id] = record
    scene_order = [str(record.get("scene_id", "")).strip() for record in records if str(record.get("scene_id", "")).strip()]
    drafts = [drafts_by_scene[scene_id] for scene_id in scene_order if scene_id in drafts_by_scene]

    save_json(visual_bible_path, visual_bible)
    save_json(drafts_path, drafts)

    project["prompts"]["visual_bible_path"] = str(visual_bible_path)
    project["prompts"]["llm_prompt_drafts_path"] = str(drafts_path)
    project["prompts"]["status"] = "draft"
    save_project(project_json, project)

    print(visual_bible_path)
    print(drafts_path)


if __name__ == "__main__":
    main()
