import argparse
import json
from pathlib import Path

from project_pipeline_utils import load_project, save_project


DEFAULT_MOTIFS = [
    "glass reflections",
    "surveillance systems",
    "documents and maps",
    "anonymous human consequence",
    "digital traces",
]


def clean_text(value: str) -> str:
    return " ".join(str(value or "").split())


def read_story_text(project: dict) -> str:
    candidates = [
        project.get("rewrite", {}).get("approved_script_path"),
        project.get("rewrite", {}).get("rewritten_script_path"),
        project.get("rewrite", {}).get("source_text_path"),
        project.get("inputs", {}).get("raw_text_path"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            text = path.read_text(encoding="utf-8-sig").strip()
            if text:
                return text
    return ""


def infer_theme(project: dict, story_text: str) -> str:
    title = clean_text(project.get("meta", {}).get("title", "")).lower()
    project_id = clean_text(project.get("project_id", "")).lower()
    joined = f"{title} {project_id} {story_text.lower()}"
    if any(marker in joined for marker in {"pantery", "panther", "jewel", "jewelry", "boutique", "diamond", "heist", "robbery"}):
        return "luxury_jewel_heist_documentary"
    if any(marker in joined for marker in {"wolf", "wolves", "wildlife", "yellowstone"}):
        return "wildlife_documentary"
    return "generic_documentary"


def make_entity(entity_id: str, entity_type: str, role: str, profile: str, usage: str) -> dict:
    return {
        "entity_id": entity_id,
        "entity_type": entity_type,
        "role": role,
        "profile": profile,
        "usage_notes": usage,
    }


def heist_continuity(scene_ids: list[str]) -> dict:
    character_profiles = [
        make_entity(
            "lead_operator",
            "character",
            "lead operator",
            "an anonymous Mediterranean-looking man in his late thirties, lean build, olive skin, short dark hair combed back, clean-shaven, calm expression, tailored charcoal suit, pale blue open-collar shirt, slim steel watch, black leather gloves when touching display surfaces",
            "Use as the recurring scout and precision mover. Keep his face unobtrusive, controlled, and never glamorized.",
        ),
        make_entity(
            "support_operator",
            "character",
            "support operator",
            "an anonymous woman in her early thirties, slim athletic build, light olive skin, dark brown bob tucked behind one ear, composed expression, fitted ivory silk blouse under a camel tailored coat, narrow gold hoop earrings, thin black gloves when near the case",
            "Use as the recurring partner. Keep the same wardrobe, build, and restrained demeanor in every appearance.",
        ),
        make_entity(
            "boutique_attendant",
            "character",
            "boutique attendant",
            "a boutique attendant in her late twenties, slim build, warm beige skin tone, neat dark hair in a low bun, black fitted blazer, white blouse, discreet diamond stud earrings, polite professional posture",
            "Use whenever staff are visible near the necklace or display case.",
        ),
        make_entity(
            "security_guard",
            "character",
            "security guard",
            "a security guard in his forties, broad build, shaved head, dark navy suit, coiled earpiece, alert posture, standing near entry chokepoints and camera sightlines",
            "Keep him grounded and procedural, never heroic.",
        ),
    ]
    object_profiles = [
        make_entity(
            "signature_necklace",
            "object",
            "signature necklace",
            "a white-gold high-jewelry necklace with a massive clear central diamond, concentric rows of smaller diamonds, deep midnight velvet mount, museum-grade finish, no visible branding or text",
            "This is the same hero object in every shot. Keep the silhouette and stone arrangement identical.",
        ),
        make_entity(
            "display_case",
            "object",
            "showroom display case",
            "a museum-grade jewelry vitrine with low-iron glass, brushed steel base, hidden magnetic lock, black velvet pedestal, immaculate reflections, no text labels",
            "Use the same case design throughout the boutique sequence.",
        ),
        make_entity(
            "surveillance_network",
            "object",
            "surveillance network",
            "ceiling dome cameras, mirrored corner lenses, discreet sensors, brushed metal door hardware, silent luxury security infrastructure",
            "Use as the recurring system motif rather than random gadgets.",
        ),
    ]
    location_profiles = [
        make_entity(
            "tokyo_boutique",
            "location",
            "luxury boutique",
            "a high-end Tokyo jewelry boutique with polished stone floors, smoked glass reflections, champagne metal frames, dark velvet display plinths, restrained warm luxury lighting, precise architectural symmetry",
            "Keep the boutique environment visually consistent across the entire sequence.",
        )
    ]

    scene_entity_map: dict[str, dict] = {}
    for index, scene_id in enumerate(scene_ids, start=1):
        active_entities = ["tokyo_boutique", "display_case", "surveillance_network"]
        focus = "preserve one coherent luxury-security world"
        if index <= 4:
            active_entities += ["signature_necklace"]
            if index == 3:
                active_entities += ["security_guard"]
        elif index <= 8:
            active_entities += ["lead_operator", "support_operator"]
            if index >= 7:
                active_entities += ["signature_necklace"]
            focus = "introduce the same two operators inside the protected boutique"
        elif index <= 12:
            active_entities += ["lead_operator", "boutique_attendant", "signature_necklace"]
            if index == 12:
                active_entities += ["support_operator"]
            focus = "keep the necklace, attendant, and scout visually identifiable across coverage"
        elif index <= 14:
            active_entities += ["boutique_attendant", "support_operator", "signature_necklace", "display_case"]
            focus = "show disruption and consequence without turning the scene into a tutorial"
        else:
            active_entities += ["lead_operator", "support_operator", "display_case"]
            focus = "show aftermath, confusion, and escape traces while keeping the same cast"

        scene_entity_map[scene_id] = {
            "active_entities": list(dict.fromkeys(active_entities)),
            "continuity_focus": focus,
        }

    return {
        "theme_hint": "luxury_jewel_heist_documentary",
        "continuity_world": "A premium investigative documentary world built around luxury security, surveillance, glass reflections, disciplined architecture, and the human cost of a fast jewel theft.",
        "recurring_motifs": [
            "glass reflections",
            "surveillance cameras",
            "silent luxury security systems",
            "anonymous affluent customers inside a controlled boutique",
            "documents, maps, and forensic traces",
        ],
        "continuity_rules": [
            "Keep recurring people and hero objects visually identical from shot to shot.",
            "Prefer anonymous, documentary-safe faces and non-glamorized criminal framing.",
            "Reuse the same boutique architecture, display case, and necklace silhouette across coverage.",
            "Keep every prompt in English and forbid visible text, signage, logos, and labels.",
            "Vary angle, scale, and light direction without changing the identity of recurring entities.",
        ],
        "character_profiles": character_profiles,
        "object_profiles": object_profiles,
        "location_profiles": location_profiles,
        "scene_entity_map": scene_entity_map,
    }


def generic_documentary_continuity(scene_ids: list[str]) -> dict:
    character_profiles = [
        make_entity(
            "primary_witness",
            "character",
            "primary witness figure",
            "an anonymous adult with neutral features, medium build, understated dark wardrobe, restrained posture, documentary-safe face with no celebrity resemblance",
            "Use the same witness profile whenever a recurring human figure is needed.",
        ),
        make_entity(
            "support_staff",
            "character",
            "support staff figure",
            "an anonymous staff member in a clean professional uniform, composed expression, practical posture, no visible text or logos",
            "Keep the same person design across repeated staff shots.",
        ),
    ]
    object_profiles = [
        make_entity(
            "hero_object",
            "object",
            "hero object",
            "one recurring key object tied to the narration, photographed with consistent materials, shape language, and surface wear, no text",
            "Keep this object visually stable whenever the story returns to it.",
        )
    ]
    location_profiles = [
        make_entity(
            "primary_location",
            "location",
            "primary location",
            "one grounded documentary environment with consistent architecture, color temperature, and physical detail",
            "Return to the same environment rather than inventing a new world for every shot.",
        )
    ]
    scene_entity_map = {
        scene_id: {
            "active_entities": ["primary_location", "hero_object", "primary_witness"],
            "continuity_focus": "reuse the same recurring witness, hero object, and environment across the sequence",
        }
        for scene_id in scene_ids
    }
    return {
        "theme_hint": "generic_documentary",
        "continuity_world": "A grounded premium documentary world with repeated people, locations, and key props that feel like one film rather than disconnected images.",
        "recurring_motifs": DEFAULT_MOTIFS,
        "continuity_rules": [
            "Keep recurring people and hero objects visually identical from shot to shot.",
            "Every prompt must stay in English and avoid visible text.",
            "Vary composition and lighting without changing who or what the recurring subject is.",
        ],
        "character_profiles": character_profiles,
        "object_profiles": object_profiles,
        "location_profiles": location_profiles,
        "scene_entity_map": scene_entity_map,
    }


def wildlife_continuity(scene_ids: list[str]) -> dict:
    pack_profile = make_entity(
        "wolf_pack",
        "character",
        "wolf pack",
        "the same grey wolf pack with winter coats, amber eyes, natural size variation, realistic anatomy, and no fantasy exaggeration",
        "Keep coat coloration and pack composition consistent across prompts.",
    )
    scene_entity_map = {
        scene_id: {
            "active_entities": ["wolf_pack", "primary_wildland"],
            "continuity_focus": "preserve the same pack and ecosystem instead of random wildlife replacements",
        }
        for scene_id in scene_ids
    }
    return {
        "theme_hint": "wildlife_documentary",
        "continuity_world": "A coherent wildlife-documentary world with one recurring pack, one ecosystem, and consistent natural light logic.",
        "recurring_motifs": ["snow tracks", "tree lines", "distance compression", "watchful stillness"],
        "continuity_rules": [
            "Keep the same recurring pack identity from shot to shot.",
            "Do not replace the main animals with random wildlife.",
            "Keep all prompts in English and avoid visible text.",
        ],
        "character_profiles": [pack_profile],
        "object_profiles": [],
        "location_profiles": [
            make_entity(
                "primary_wildland",
                "location",
                "primary wildland",
                "one consistent cold-weather ecosystem with conifers, snow, open meadows, and believable topography",
                "Reuse the same geography across neighboring shots.",
            )
        ],
        "scene_entity_map": scene_entity_map,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    continuity_bible_path = Path(project["planning"]["continuity_bible_md_path"])
    continuity_entities_path = Path(project["planning"]["continuity_map_json_path"])
    continuity_bible_path.parent.mkdir(parents=True, exist_ok=True)

    scene_ids: list[str] = []
    segment_ids: list[int] = []
    storyboard_path = Path(project["planning"]["storyboard_path"])
    scene_plan_path = Path(project["scene_plan"]["scene_plan_path"])
    if storyboard_path.exists():
        storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
        scene_ids = [str(item["scene_id"]) for item in storyboard.get("items", [])]
        segment_ids = [int(item["segment_id"]) for item in storyboard.get("items", [])]
    elif scene_plan_path.exists():
        scene_plan = json.loads(scene_plan_path.read_text(encoding="utf-8"))
        scene_ids = [str(scene["scene_id"]) for scene in scene_plan.get("scenes", [])]
        segment_ids = [int(scene["source_segment_id"]) for scene in scene_plan.get("scenes", [])]
    story_text = read_story_text(project)
    theme = infer_theme(project, story_text)

    if theme == "luxury_jewel_heist_documentary":
        continuity = heist_continuity(scene_ids)
    elif theme == "wildlife_documentary":
        continuity = wildlife_continuity(scene_ids)
    else:
        continuity = generic_documentary_continuity(scene_ids)

    entities = {
        "project_id": project["project_id"],
        "theme_hint": continuity["theme_hint"],
        "continuity_world": continuity["continuity_world"],
        "prompt_language": "English",
        "scene_count": len(scene_ids),
        "recurring_motifs": continuity["recurring_motifs"],
        "continuity_rules": continuity["continuity_rules"],
        "character_profiles": continuity["character_profiles"],
        "object_profiles": continuity["object_profiles"],
        "location_profiles": continuity["location_profiles"],
        "scene_entity_map": continuity["scene_entity_map"],
        "segment_entity_map": {
            str(segment_id): continuity["scene_entity_map"].get(scene_id, {})
            for scene_id, segment_id in zip(scene_ids, segment_ids)
        },
    }

    lines = [
        "# Continuity Bible",
        "",
        f"Theme: {entities['theme_hint']}",
        "",
        "## Continuity World",
        entities["continuity_world"],
        "",
        "## Rules",
    ]
    lines.extend(f"- {item}" for item in entities["continuity_rules"])
    lines.extend(["", "## Recurring Motifs"])
    lines.extend(f"- {item}" for item in entities["recurring_motifs"])
    lines.extend(["", "## Character Profiles"])
    lines.extend(
        f"- {item['entity_id']}: {item['profile']}"
        for item in entities["character_profiles"]
    )
    lines.extend(["", "## Object Profiles"])
    lines.extend(
        f"- {item['entity_id']}: {item['profile']}"
        for item in entities["object_profiles"]
    )

    continuity_bible_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    continuity_entities_path.write_text(json.dumps(entities, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    project["planning"]["status"] = "continuity_map_built"
    project["current_stage"] = "allocate_frames"
    save_project(project_json, project)
    print(continuity_entities_path)
    print(continuity_bible_path)


if __name__ == "__main__":
    main()
