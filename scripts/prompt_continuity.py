import hashlib
import json
import re
from pathlib import Path


STYLE_SUMMARY = (
    "Premium cinematic documentary still, photorealistic, realistic lens perspective, atmospheric depth, "
    "natural imperfections, 16:9 composition, no text."
)

ABSTRACT_PRIMARY_SUBJECTS = {
    "the recurring documentary subject",
    "the same recurring documentary subject inside the same environment",
}


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("\n", " ")).strip()


def stable_hash(payload: object) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def read_source_text(project: dict) -> str:
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


def infer_theme(project: dict, source_text: str, scenes: list[dict]) -> str:
    title = clean_text(project.get("meta", {}).get("title", "")).lower()
    project_id = clean_text(project.get("project_id", "")).lower()
    joined = " ".join(clean_text(scene.get("voice_text", "")) for scene in scenes).lower()
    blob = f"{title} {project_id} {source_text.lower()} {joined}"
    if any(
        marker in blob
        for marker in {
            "panter",
            "panther",
            "розов",
            "pink",
            "jewel",
            "diamond",
            "boutique",
            "heist",
            "robbery",
            "tokyo",
            "бриллиант",
            "бутик",
            "ограблен",
        }
    ):
        return "luxury_jewel_heist_documentary"
    return "generic_documentary"


def jewel_heist_bundle() -> dict:
    return {
        "theme_hint": "luxury_jewel_heist_documentary",
        "continuity_world": (
            "A premium investigative documentary world built around luxury security, surveillance, glass reflections, "
            "disciplined architecture, and the human cost of a fast jewel theft."
        ),
        "continuity_rules": [
            "Repeat the same character and object descriptions verbatim whenever those entities return.",
            "Do not introduce random new faces if a recurring role already exists.",
            "Every prompt must include style, atmosphere, lighting, and angle.",
            "No visible text, logos, watermarks, or real-person names.",
            "Event-specific scenes must prioritize readable action over safe continuity filler.",
        ],
        "recurring_motifs": [
            "glass reflections",
            "surveillance cameras",
            "silent luxury security systems",
            "investigative evidence fragments",
        ],
        "character_profiles": [
            {
                "entity_id": "lead_operator",
                "profile": "an anonymous Mediterranean-looking man in his late thirties, lean build, olive skin, short dark hair combed back, clean-shaven, calm expression, tailored charcoal suit, pale blue open-collar shirt, slim steel watch, black leather gloves when touching display surfaces",
            },
            {
                "entity_id": "support_operator",
                "profile": "an anonymous woman in her early thirties, slim athletic build, light olive skin, dark brown bob tucked behind one ear, composed expression, fitted ivory silk blouse under a camel tailored coat, narrow gold hoop earrings, thin black gloves when near the case",
            },
            {
                "entity_id": "boutique_attendant",
                "profile": "a boutique attendant in her late twenties, neat dark hair in a low bun, understated black uniform dress, white silk neck scarf, attentive professional posture, careful gloved handling near the jewelry case",
            },
            {
                "entity_id": "security_guard",
                "profile": "a security guard in his forties, broad build, shaved head, dark navy suit, coiled earpiece, alert posture, standing near entry chokepoints and camera sightlines",
            },
            {
                "entity_id": "investigator",
                "profile": "an anonymous investigator in neutral workwear, sleeves rolled, careful posture, handling evidence and route fragments without showing any readable text",
            },
        ],
        "object_profiles": [
            {
                "entity_id": "display_case",
                "profile": "a museum-grade jewelry vitrine with low-iron glass, brushed steel base, hidden magnetic lock, black velvet pedestal, immaculate reflections, no text labels",
            },
            {
                "entity_id": "signature_necklace",
                "profile": "a white-gold high-jewelry necklace with a massive clear central diamond, concentric rows of smaller diamonds, deep midnight velvet mount, museum-grade finish, no visible branding or text",
            },
            {
                "entity_id": "surveillance_network",
                "profile": "ceiling dome cameras, mirrored corner lenses, discreet sensors, brushed metal door hardware, silent luxury security infrastructure",
            },
            {
                "entity_id": "cream_jar_evidence",
                "profile": "an unbranded cream jar used as concealment evidence, matte lid, realistic cosmetic wear, a jewel compartment implied without readable packaging text",
            },
            {
                "entity_id": "route_fragments",
                "profile": "maps, transit fragments, architectural plans, and route traces arranged as cinematic evidence with no readable text",
            },
        ],
        "location_profiles": [
            {
                "entity_id": "tokyo_boutique",
                "profile": "a high-end Tokyo jewelry boutique with polished stone floors, smoked glass reflections, champagne metal frames, dark velvet display plinths, restrained warm luxury lighting, precise architectural symmetry",
            },
            {
                "entity_id": "boutique_threshold",
                "profile": "the boutique threshold and escape corridor just beyond the display floor, reflective stone, security hardware, compressed exit geometry, and the sense of delayed response",
            },
            {
                "entity_id": "tokyo_night_city",
                "profile": "Tokyo at night in 2004, layered expressways, sodium-lit facades, surveillance vantage points, humid urban air, and institutional scale without readable signage",
            },
            {
                "entity_id": "investigation_room",
                "profile": "a restrained investigative workspace with desk lamps, maps, route fragments, evidence trays, brushed metal surfaces, and no readable text",
            },
            {
                "entity_id": "evidence_table",
                "profile": "a forensic tabletop evidence setup with neutral surfaces, careful gloved handling, premium object detail, and no readable text or labels",
            },
            {
                "entity_id": "transnational_network_space",
                "profile": "a realistic transnational logistics and coordination environment combining transit fragments, anonymous operators, luggage traces, parked vehicles, and muted operational lighting without tutorial detail",
            },
        ],
    }


def generic_bundle(project: dict) -> dict:
    title = clean_text(project.get("meta", {}).get("title", "")) or "the documentary subject"
    return {
        "theme_hint": "generic_documentary",
        "continuity_world": (
            "A grounded documentary world with recurring people, objects, and locations that should stay visually stable "
            "from frame to frame."
        ),
        "continuity_rules": [
            "Repeat the same character and object descriptions verbatim whenever those entities return.",
            "Do not introduce random replacement people.",
            "Every prompt must include style, atmosphere, lighting, and angle.",
            "No visible text, logos, watermarks, or real-person names.",
        ],
        "recurring_motifs": [
            "layered foreground and background storytelling",
            "observational documentary realism",
            "coherent recurring locations",
        ],
        "character_profiles": [
            {
                "entity_id": "primary_subject",
                "profile": f"an anonymous recurring documentary subject connected to {title}, natural appearance, grounded clothing, consistent face shape, consistent hairstyle, realistic posture",
            }
        ],
        "object_profiles": [],
        "location_profiles": [
            {
                "entity_id": "primary_location",
                "profile": "a grounded real-world environment tied to the narration, realistic textures, motivated practical lighting, no visible text",
            }
        ],
    }


def detect_semantic_flags(text: str) -> dict[str, bool]:
    lowered = clean_text(text).lower()
    flags = {
        "spray_attack": any(token in lowered for token in ["газ", "ослеп", "раздражающ", "spray", "blinded", "mist"]),
        "open_case": any(token in lowered for token in ["витрина открыта", "открыта", "open case", "case open"]),
        "missing_jewel": any(token in lowered for token in ["исчез", "пропал", "missing", "gone"]),
        "attendant_action": any(token in lowered for token in ["сотруд", "attendant"]),
        "access_opening": any(token in lowered for token in ["доступ", "открывает", "открыл", "unlock"]),
        "operator_entry": any(token in lowered for token in ["входят", "двое", "клиент", "entered", "pair"]),
        "delayed_reaction": any(token in lowered for token in ["пытаются понять", "что случилось", "не успевает", "too late", "trying to understand"]),
        "operator_exit": any(token in lowered for token in ["уходят", "already leaving", "exit", "escape"]),
        "historical_context": any(token in lowered for token in ["токио", "2004", "japan", "tokyo"]),
        "institutional_response": any(token in lowered for token in ["полици", "система", "решение", "police", "system", "decision"]),
        "nickname_identity": any(token in lowered for token in ["розовыми пантерами", "розовую пантеру", "pink panther", "их прозвали"]),
        "object_evidence": any(token in lowered for token in ["баночке с кремом", "кремом", "cream jar", "баночк"]),
        "anti_myth": any(token in lowered for token in ["не потому", "романтический кодекс", "headquarters", "uniform"]),
        "network_scale": any(token in lowered for token in ["балкан", "сеть", "бывших военных", "логистик", "network", "balkan"]),
        "mechanism_focus": any(token in lowered for token in ["механизм", "архитектур", "человеческую реакцию", "бюрократи", "human reaction", "bureaucracy"]),
        "security_system": any(token in lowered for token in ["охрана", "камеры", "магнитн", "security", "surveillance"]),
        "boutique_luxury": any(token in lowered for token in ["бутик", "витрин", "бриллиант", "колье", "display", "boutique", "diamond", "necklace"]),
        "comedic_contrast": any(token in lowered for token in ["не комедия", "почти комедийным", "not comedy", "comic"]),
    }
    flags["theft_reveal"] = flags["open_case"] or flags["missing_jewel"]
    flags["reaction_escape"] = flags["delayed_reaction"] or flags["operator_exit"]
    flags["content_payload"] = any(
        value
        for key, value in flags.items()
        if key not in {"boutique_luxury", "security_system"}
    )
    return flags


def infer_event_type(flags: dict[str, bool], shot_index: int) -> tuple[str, float, str]:
    if flags["spray_attack"]:
        return "assault", 0.98, ""
    if flags["theft_reveal"]:
        return "theft_reveal", 0.96, ""
    if flags["reaction_escape"]:
        return "reaction_escape", 0.94, ""
    if flags["historical_context"]:
        return "historical_context", 0.95, ""
    if flags["nickname_identity"]:
        return "identity_reveal", 0.94, ""
    if flags["object_evidence"]:
        return "object_evidence", 0.97, ""
    if flags["anti_myth"]:
        return "anti_myth", 0.9, ""
    if flags["comedic_contrast"]:
        return "hidden_threat", 0.9, ""
    if flags["network_scale"]:
        return "network_scale", 0.93, ""
    if flags["mechanism_focus"]:
        return "mechanism_focus", 0.93, ""
    if flags["institutional_response"]:
        return "system_delay", 0.88, ""
    if flags["access_opening"]:
        return "necklace_access", 0.95, ""
    if flags["operator_entry"]:
        return "operator_entry", 0.9, ""
    if flags["security_system"] and shot_index <= 6:
        return "security_system", 0.85, ""
    if flags["boutique_luxury"] and shot_index <= 6:
        return "luxury_establishing", 0.82, ""
    return "explicit_transition", 0.35, "No strong semantic event markers found; transition fallback used."


def infer_part_semantic_role(event_type: str, part_index: int, parts_total: int) -> str:
    if parts_total <= 1:
        return "single"
    if event_type == "assault":
        return "moment" if part_index == 1 else "aftermath"
    if event_type == "theft_reveal":
        return "moment" if part_index == 1 else "aftermath"
    if event_type == "reaction_escape":
        if part_index == 1:
            return "reaction"
        if part_index == parts_total:
            return "escape"
        return "system_delay"
    if event_type == "historical_context":
        return "identity_context"
    if event_type == "system_delay":
        return "reaction" if part_index == 1 else "system_delay"
    if event_type == "anti_myth":
        return "reaction" if part_index == 1 else "identity_context"
    if event_type == "hidden_threat":
        if part_index == 1:
            return "reaction"
        if part_index == parts_total:
            return "mechanism"
        return "network"
    if event_type == "network_scale":
        return "network" if part_index < parts_total else "mechanism"
    if event_type == "mechanism_focus":
        return "mechanism"
    if event_type == "object_evidence":
        return "moment" if part_index == 1 else "identity_context"
    return "transition"


def semantic_defaults(event_type: str, part_role: str) -> tuple[str, bool, str, str]:
    mapping = {
        "assault": ("attendant blinded by irritant spray inside the boutique", True, "emotion", "tension_detail"),
        "theft_reveal": ("open case and immediate absence of the necklace", True, "payoff", "before_after_contrast"),
        "reaction_escape": (
            "humans process too slowly while operators are already leaving the scene",
            False,
            "contrast" if part_role == "reaction" else "transition",
            "human_consequence",
        ),
        "historical_context": ("place the heist in Tokyo 2004 with institutional scale", False, "explain", "scale_contrast"),
        "identity_reveal": ("explain how the Pink Panthers identity emerges from evidence and consequence", False, "evidence", "evidence_wall"),
        "object_evidence": ("show the cream-jar concealment as concrete criminal evidence", True, "evidence", "evidence_wall"),
        "anti_myth": ("reject romantic mythology and strip the story down to criminal reality", False, "contrast", "before_after_contrast"),
        "hidden_threat": ("show the darker criminal reality hiding behind the almost comic anecdote", False, "contrast", "before_after_contrast"),
        "network_scale": ("expand from one robbery to a coordinated transnational network", False, "explain", "mechanism_view"),
        "mechanism_focus": ("shift from legend to operational mechanism and system exploitation", False, "explain", "mechanism_view"),
        "system_delay": ("show institutional delay and slower decision-making compared with the operators", False, "explain", "mechanism_view"),
        "necklace_access": ("show the controlled access ritual at the display case", True, "explain", "evidence_wall"),
        "operator_entry": ("introduce the operators as composed affluent customers under surveillance", False, "pattern_break", "human_consequence"),
        "security_system": ("show security architecture as a silent controlling mechanism", False, "evidence", "mechanism_view"),
        "luxury_establishing": ("establish the luxury-security world and the value at risk", False, "hook", "mechanism_view"),
        "explicit_transition": ("use a controlled transition image without losing world continuity", False, "transition", "literal_premium"),
    }
    return mapping[event_type]


def extract_scene_semantics(scene: dict, theme_hint: str) -> dict:
    text = clean_text(scene.get("voice_text", ""))
    shot_index = int(scene.get("shot_index", 0) or 0)
    flags = detect_semantic_flags(text)
    event_type, role_confidence, fallback_reason = infer_event_type(flags, shot_index)
    part_role = infer_part_semantic_role(event_type, int(scene.get("part_index", 1) or 1), int(scene.get("parts_total", 1) or 1))
    semantic_action, event_clarity_required, visual_function, visual_strategy = semantic_defaults(event_type, part_role)
    return {
        "semantic_action": semantic_action,
        "event_type": event_type,
        "event_clarity_required": event_clarity_required,
        "visual_function": visual_function,
        "visual_strategy": visual_strategy,
        "role_confidence": role_confidence,
        "fallback_reason": fallback_reason,
        "part_semantic_role": part_role,
        "semantic_flags": flags,
        "semantic_valid": not (theme_hint == "luxury_jewel_heist_documentary" and event_type == "explicit_transition" and flags["content_payload"]),
    }


def build_scene_entity_entry(scene: dict, descriptor: dict, theme: str) -> dict:
    if theme != "luxury_jewel_heist_documentary":
        return {
            "active_entities": ["primary_location", "primary_subject"],
            "continuity_focus": "preserve one coherent documentary world",
        }

    event_type = descriptor["event_type"]
    active = ["surveillance_network"]
    focus = "preserve one coherent luxury-security world"

    if event_type in {"luxury_establishing", "security_system", "necklace_access", "assault", "theft_reveal"}:
        active.extend(["tokyo_boutique", "display_case"])
    if event_type in {"luxury_establishing", "necklace_access", "theft_reveal", "identity_reveal"}:
        active.append("signature_necklace")
    if event_type in {"operator_entry", "assault", "reaction_escape", "network_scale", "mechanism_focus", "hidden_threat"}:
        active.extend(["lead_operator", "support_operator"])
    if event_type in {"necklace_access", "assault", "reaction_escape", "theft_reveal"}:
        active.append("boutique_attendant")
    if event_type in {"security_system", "historical_context"}:
        active.append("security_guard")
    if event_type == "historical_context":
        active.append("tokyo_night_city")
        focus = "shift from the boutique event to historical city context and institutional response"
    if event_type == "reaction_escape":
        active.append("boutique_threshold")
        focus = "show delayed reaction inside the room while the operators are already escaping"
    if event_type in {"system_delay", "mechanism_focus", "hidden_threat"}:
        active.extend(["investigation_room", "investigator", "route_fragments"])
        focus = "show slow institutional reasoning and mechanism analysis instead of the boutique interior"
    if event_type == "identity_reveal":
        active.extend(["investigation_room", "investigator", "signature_necklace"])
        focus = "introduce the Pink Panthers identity through evidence and consequence"
    if event_type == "object_evidence":
        active.extend(["evidence_table", "investigator", "cream_jar_evidence", "signature_necklace"])
        focus = "use the cream-jar evidence as the pattern break that explains the name"
    if event_type == "anti_myth":
        active.extend(["investigation_room", "route_fragments", "investigator"])
        focus = "reject romantic myth and strip the story down to criminal reality"
    if event_type == "hidden_threat":
        active.extend(["transnational_network_space", "route_fragments", "investigation_room"])
        focus = "turn the almost comic anecdote into a doorway toward the network's darker reality"
    if event_type == "network_scale":
        active.extend(["transnational_network_space", "route_fragments"])
        focus = "move from one heist to the wider network and logistical coordination"
    if event_type == "explicit_transition":
        active.extend(["tokyo_boutique", "display_case"])
        focus = "use a transition only because no stronger semantic action was detected"

    return {
        "active_entities": list(dict.fromkeys(active)),
        "continuity_focus": focus,
    }


def profile_map(entities: list[dict]) -> dict[str, dict]:
    return {item["entity_id"]: item for item in entities}


def infer_shot_role(scene: dict, scene_entry: dict, descriptor: dict, theme: str) -> str:
    if theme != "luxury_jewel_heist_documentary":
        return "documentary_bridge"

    event_type = descriptor["event_type"]
    part_role = descriptor["part_semantic_role"]
    if event_type == "assault":
        return "assault_aftermath" if part_role == "aftermath" else "assault_moment"
    if event_type == "theft_reveal":
        return "empty_case_aftermath" if part_role == "aftermath" else "empty_case_reveal"
    if event_type == "reaction_escape":
        if part_role == "reaction":
            return "delayed_reaction"
        if part_role == "escape":
            return "operator_exit"
        return "system_delay"
    if event_type == "historical_context":
        return "historical_context"
    if event_type == "identity_reveal":
        return "identity_reveal"
    if event_type == "object_evidence":
        return "object_evidence"
    if event_type == "anti_myth":
        return "myth_rejection"
    if event_type == "hidden_threat":
        if part_role == "reaction":
            return "menace_under_myth"
        if part_role == "network":
            return "network_introduction"
        return "investigative_mechanism"
    if event_type == "network_scale":
        return "investigative_mechanism" if part_role == "mechanism" else "network_introduction"
    if event_type == "mechanism_focus":
        return "investigative_mechanism"
    if event_type == "system_delay":
        return "institutional_realization" if part_role == "reaction" else "system_delay"
    if event_type == "necklace_access":
        return "necklace_access"
    if event_type == "operator_entry":
        return "operator_entry"
    if event_type == "security_system":
        return "security_system"
    if event_type == "luxury_establishing":
        return "luxury_establishing"
    if event_type == "explicit_transition":
        if descriptor["semantic_flags"]["content_payload"]:
            raise ValueError(f"Scene {scene['scene_id']} contains semantic payload but fell into transition fallback")
        return "investigative_bridge"
    return "investigative_bridge"


def build_blueprint(shot_role: str, shot_index: int, theme: str) -> dict:
    if theme != "luxury_jewel_heist_documentary":
        return {
            "scene_meaning": "Translate the narration into one coherent documentary shot inside a recurring visual world.",
            "action": "Show one clear observable action or state connected to the narration while preserving the same recurring subject design.",
            "composition": "one recurring subject framed with readable depth and grounded context",
            "angle": "medium documentary angle",
            "lighting": "motivated practical lighting",
            "atmosphere": "coherent, grounded, cinematic",
            "visual_goal": "Keep the visual world consistent across the sequence.",
        }

    mapping = {
        "luxury_establishing": {
            "scene_meaning": "Establish the boutique as a meticulously protected luxury environment with value and tension already baked into the space.",
            "action": "Show the boutique as a machine of luxury security rather than a simple store interior.",
            "composition": "layered foreground reflections, controlled symmetry, hero object protected inside the frame",
            "angle": "wide architectural documentary angle" if shot_index == 1 else "top-down surveillance angle",
            "lighting": "restrained warm luxury lighting mixed with colder security highlights",
            "atmosphere": "tense, premium, investigative",
            "visual_goal": "Make the space feel expensive, guarded, and narratively dangerous.",
        },
        "security_system": {
            "scene_meaning": "Reveal the hidden system that watches the room and controls access.",
            "action": "Translate security logic into a visual network of cameras, locks, and guard presence.",
            "composition": "foreground hardware detail with guard or reflected boutique depth behind it",
            "angle": "over-the-shoulder documentary angle",
            "lighting": "cool security spill with warm boutique accents",
            "atmosphere": "controlled, watchful, procedural",
            "visual_goal": "Show surveillance as a character in the film.",
        },
        "operator_entry": {
            "scene_meaning": "Introduce the same two operators as composed affluent customers who do not belong emotionally to the room.",
            "action": "Show the pair entering the controlled boutique world while still blending in.",
            "composition": "one operator leading, the other slightly behind, with display glass and cameras framing them",
            "angle": "medium documentary angle at eye level",
            "lighting": "motivated boutique light with subtle cold reflections on glass",
            "atmosphere": "quietly threatening, controlled, elegant",
            "visual_goal": "Make the recurring pair feel stable and recognisable across the story.",
        },
        "necklace_access": {
            "scene_meaning": "Show the exact moment the attendant opens controlled access to the necklace display.",
            "action": "Show the attendant actively opening the protected case while the necklace, lock hardware, and observing operator remain readable in the same frame, without becoming tutorial-like.",
            "composition": "the opening gesture and access hardware are instantly readable, with the necklace and partial human presence anchored in the same controlled frame",
            "angle": "close documentary angle" if shot_index < 11 else "macro evidence angle",
            "lighting": "tight gallery spotlight with soft edge reflections",
            "atmosphere": "precise, tense, forensic",
            "visual_goal": "Make the access ritual readable in one glance.",
        },
        "assault_moment": {
            "scene_meaning": "Show the exact instant the boutique attendant is hit by the blinding irritant, with the action readable in one frame.",
            "action": "Show the attendant recoiling as the irritant mist hits, with the support operator partially visible and the protected display case still in frame.",
            "composition": "the attendant's recoil and the burst of irritant are instantly readable, with the case and operator placement anchoring the geography",
            "angle": "tight over-the-shoulder action angle",
            "lighting": "luxury interior light fractured by harsh specular reflections and sudden motion",
            "atmosphere": "violent, immediate, documentary-real",
            "visual_goal": "Prioritize event clarity over abstraction.",
        },
        "assault_aftermath": {
            "scene_meaning": "Show the immediate aftermath of the blinding spray while keeping the attack geography unmistakable.",
            "action": "Show the attendant disoriented and off-balance a fraction of a second after impact, with lingering irritant haze, the support operator still in the scene, and the display case anchoring the location.",
            "composition": "the attendant's disorientation stays readable while the case, haze, and operator positions preserve the exact continuity of the attack beat",
            "angle": "close aftermath documentary angle",
            "lighting": "fractured luxury light with suspended haze and sharper contrast around the case",
            "atmosphere": "disoriented, urgent, unstable",
            "visual_goal": "Hold the consequence of the spray without delaying the first readable impact.",
        },
        "empty_case_reveal": {
            "scene_meaning": "Show the open case and the immediate realization that the jewel is gone.",
            "action": "Show the now-open display case with the necklace missing, while hands, reflections, or blurred staff movement convey immediate chaos.",
            "composition": "the empty pedestal dominates the frame while partial figures and reflections deliver the emotional fallout",
            "angle": "close forensic documentary angle",
            "lighting": "tight gallery light on the empty mount with colder spill in the background",
            "atmosphere": "forensic, stunned, urgent",
            "visual_goal": "Make the absence of the jewel unmistakable.",
        },
        "empty_case_aftermath": {
            "scene_meaning": "Show the first shockwave after the empty case reveal, when the theft is already understood.",
            "action": "Show the open case still empty while hands, reflections, and disrupted staff movement make the loss feel immediate and irreversible.",
            "composition": "the empty mount remains dominant but the surrounding human reaction and spatial disturbance now carry more weight",
            "angle": "wider aftermath forensic angle",
            "lighting": "tight gallery light on the empty mount with cooler spill spreading across the room",
            "atmosphere": "stunned, escalating, chaotic",
            "visual_goal": "Extend the theft reveal into consequence rather than repeating the same empty-case beat.",
        },
        "delayed_reaction": {
            "scene_meaning": "Show the audience and staff still trying to understand the attack while the operators already have a head start.",
            "action": "Show human hesitation, partial disorientation, and fragmented attention around the boutique floor before the room has mentally caught up.",
            "composition": "foreground reaction detail with blurred escape vectors or threshold geometry hinting that the decisive moment has already passed",
            "angle": "medium aftermath documentary angle",
            "lighting": "unstable boutique light with reactive reflections and slight haze residue",
            "atmosphere": "lagging, disoriented, too late",
            "visual_goal": "Make delayed human comprehension feel like a tactical weakness.",
        },
        "operator_exit": {
            "scene_meaning": "Show that the operators are already leaving while the room is still processing what happened.",
            "action": "Show the operators at or beyond the boutique threshold with no glamorized heroism, while the reaction behind them remains spatially connected but slower.",
            "composition": "exit geometry dominates, with the operators already separating from the chaos they caused",
            "angle": "compressed exit-corridor documentary angle",
            "lighting": "cooler threshold light with boutique reflections dying behind them",
            "atmosphere": "efficient, cold, irreversible",
            "visual_goal": "Make speed asymmetry between crime and response visually obvious.",
        },
        "historical_context": {
            "scene_meaning": "Shift from the boutique incident to a precise historical and geographic context.",
            "action": "Show Tokyo as a controlled urban system at night, linking the crime scene to time, place, and institutional scale without using text.",
            "composition": "city-scale frame with layered surveillance or civic infrastructure details anchoring the location",
            "angle": "wide elevated city documentary angle",
            "lighting": "night urban light with sodium and cool security tones",
            "atmosphere": "historical, analytical, tense",
            "visual_goal": "Make the viewer feel that this event belongs to a real time and city, not just one room.",
        },
        "institutional_realization": {
            "scene_meaning": "Show the first institutional realization that the problem is bigger than one boutique and that the system is late.",
            "action": "Use investigators, surveillance fragments, or route evidence to convey that official understanding is arriving after the decisive moment.",
            "composition": "human analyst or evidence foreground with delayed institutional geometry behind it",
            "angle": "over-the-shoulder investigative response angle",
            "lighting": "cold desk light against dim ambient spill",
            "atmosphere": "belated, analytical, uneasy",
            "visual_goal": "Translate narration about the system admitting weakness into a specific readable image.",
        },
        "system_delay": {
            "scene_meaning": "Make the system itself feel slower and heavier than the operators it is trying to understand.",
            "action": "Show fragmented routes, architecture, and procedural analysis as a machine that reacts after the decisive action is over.",
            "composition": "structured mechanism frame with route fragments, architecture cues, and human analysis arranged without readable text",
            "angle": "mechanism-analysis documentary angle",
            "lighting": "controlled operational light with cool contrast and practical highlights",
            "atmosphere": "slow, procedural, outpaced",
            "visual_goal": "Make 'criminals move faster than the system' visually legible without repeating the boutique interior.",
        },
        "identity_reveal": {
            "scene_meaning": "Introduce the identity of the Pink Panthers as a transnational criminal myth forming out of a specific case.",
            "action": "Show the transition from one jewel theft to the recognisable criminal identity attached to it, using recurring luxury evidence rather than repeating the attack.",
            "composition": "hero evidence object with layered reflections, investigative framing, and symbolic but realistic context",
            "angle": "close documentary evidence angle",
            "lighting": "controlled gallery light mixed with cooler investigative spill",
            "atmosphere": "revealing, myth-building, forensic",
            "visual_goal": "Make the nickname feel earned by evidence and consequence, not by repeating the first heist beat.",
        },
        "myth_rejection": {
            "scene_meaning": "Reject the glamorous myth and make clear that the network is not a romantic criminal brotherhood.",
            "action": "Show absence of uniforms, headquarters, and ritualized identity through stripped-down evidence or anonymous operational traces instead of glamorous character posing.",
            "composition": "clean contrast frame where missing mythology is communicated through ordinary but disciplined criminal traces",
            "angle": "restrained investigative contrast angle",
            "lighting": "neutral investigative light with cooler shadows",
            "atmosphere": "demythologized, sober, corrective",
            "visual_goal": "Push the film away from heist fantasy and toward investigative reality.",
        },
        "menace_under_myth": {
            "scene_meaning": "Show that the almost comic anecdote hides something colder, harder, and more disciplined.",
            "action": "Translate the shift from comic surface to criminal seriousness through anonymous operational traces, stripped emotion, and the absence of glamour.",
            "composition": "foreground trace of the anecdote with darker operational context taking over the frame",
            "angle": "close investigative turn angle",
            "lighting": "cooler contrast with the warmth drained out of the earlier anecdotal image",
            "atmosphere": "sobering, ominous, corrective",
            "visual_goal": "Make the audience feel the story harden from anecdote into threat.",
        },
        "object_evidence": {
            "scene_meaning": "Turn the cream-jar anecdote into a concrete piece of criminal evidence rather than a repeated boutique shot.",
            "action": "Show a realistic evidence-style object composition built around a cream jar, a concealed jewel, packaging detail, and investigative handling, with no readable text.",
            "composition": "macro tabletop evidence composition with one key object dominating the frame",
            "angle": "macro forensic tabletop angle",
            "lighting": "soft top light with cool edge shadows and reflective highlights",
            "atmosphere": "forensic, surprising, precise",
            "visual_goal": "Create a strong pattern break that explains the name without recycling boutique imagery.",
        },
        "network_introduction": {
            "scene_meaning": "Expand from one robbery to a disciplined transnational network of roles, logistics, and trusted coordination.",
            "action": "Show an investigative view of a distributed transnational organization through recurring operator archetypes, travel traces, maps, vehicles, and logistical coordination without becoming instructional.",
            "composition": "layered multi-plane frame with people, routes, and operational artifacts suggesting a distributed network",
            "angle": "medium-wide investigative ensemble angle",
            "lighting": "cold operational light with selective warm highlights",
            "atmosphere": "organized, transnational, controlled",
            "visual_goal": "Make the audience feel the scale and structure of the network beyond the first boutique incident.",
        },
        "investigative_mechanism": {
            "scene_meaning": "Pivot from myth to mechanism and announce that the film is about how the system worked.",
            "action": "Show investigative breakdown elements like routes, architectural lines, reactions, and procedural fragments arranged as a cinematic mechanism view, not a text-heavy board.",
            "composition": "structured mechanism frame with foreground evidence details and background system geometry",
            "angle": "over-the-shoulder investigative analysis angle",
            "lighting": "controlled desk light and cold ambient spill",
            "atmosphere": "analytical, high-retention, investigative",
            "visual_goal": "Make the second minute clearly evolve into analysis instead of replaying the robbery.",
        },
        "investigative_bridge": {
            "scene_meaning": "Use a narrow transition image only because the narration truly contains no stronger semantic beat.",
            "action": "Bridge adjacent beats through the same world without introducing new meaning that contradicts the narration.",
            "composition": "controlled transition frame with continuity-safe objects and a clearly secondary role in the sequence",
            "angle": "medium documentary transition angle",
            "lighting": "motivated continuity lighting",
            "atmosphere": "restrained, connective, secondary",
            "visual_goal": "Support continuity without replacing a missing semantic beat.",
        },
    }
    return mapping[shot_role]


def resolve_environment(active_ids: list[str], location_map: dict[str, dict], shot_role: str, theme: str) -> str:
    if theme != "luxury_jewel_heist_documentary":
        return location_map.get("primary_location", {}).get(
            "profile", "a grounded documentary environment tied to the narration"
        )

    preferred_map = {
        "historical_context": "tokyo_night_city",
        "delayed_reaction": "tokyo_boutique",
        "operator_exit": "boutique_threshold",
        "institutional_realization": "investigation_room",
        "system_delay": "investigation_room",
        "identity_reveal": "investigation_room",
        "myth_rejection": "investigation_room",
        "menace_under_myth": "investigation_room",
        "object_evidence": "evidence_table",
        "network_introduction": "transnational_network_space",
        "investigative_mechanism": "investigation_room",
    }
    preferred = preferred_map.get(shot_role)
    if preferred and preferred in location_map:
        return location_map[preferred]["profile"]
    for entity_id in active_ids:
        if entity_id in location_map:
            return location_map[entity_id]["profile"]
    return "a grounded investigative documentary environment with no readable text"


def build_continuity_bundle(project: dict, scenes: list[dict], source_text: str) -> dict:
    theme = infer_theme(project, source_text, scenes)
    bundle = jewel_heist_bundle() if theme == "luxury_jewel_heist_documentary" else generic_bundle(project)
    scene_entity_map = {}
    shot_role_map = {}
    semantics_map = {}
    for scene in scenes:
        descriptor = extract_scene_semantics(scene, bundle["theme_hint"])
        semantics_map[scene["scene_id"]] = descriptor
        scene_entry = build_scene_entity_entry(scene, descriptor, bundle["theme_hint"])
        scene_entity_map[scene["scene_id"]] = scene_entry
        shot_role_map[scene["scene_id"]] = infer_shot_role(scene, scene_entry, descriptor, bundle["theme_hint"])
    bundle["scene_entity_map"] = scene_entity_map
    bundle["scene_semantics_map"] = semantics_map
    bundle["shot_role_map"] = shot_role_map
    return bundle


def build_scene_prompt(scene: dict, bundle: dict) -> dict:
    scene_entry = bundle["scene_entity_map"][scene["scene_id"]]
    descriptor = bundle["scene_semantics_map"][scene["scene_id"]]
    shot_role = bundle["shot_role_map"][scene["scene_id"]]
    blueprint = build_blueprint(shot_role, int(scene.get("shot_index", 0)), bundle["theme_hint"])

    char_map = profile_map(bundle["character_profiles"])
    object_map = profile_map(bundle["object_profiles"])
    location_map = profile_map(bundle["location_profiles"])
    active_ids = scene_entry["active_entities"]

    profiles = []
    for entity_id in active_ids:
        if entity_id in char_map:
            profiles.append(f"- {entity_id}: {char_map[entity_id]['profile']}")
        elif entity_id in object_map:
            profiles.append(f"- {entity_id}: {object_map[entity_id]['profile']}")
        elif entity_id in location_map:
            profiles.append(f"- {entity_id}: {location_map[entity_id]['profile']}")

    primary_subject_map = {
        "operator_entry": "the same two operators moving through the boutique under surveillance",
        "assault_moment": "the boutique attendant being blinded in the instant of the attack",
        "assault_aftermath": "the boutique attendant reeling in the immediate aftermath of the blinding spray",
        "empty_case_reveal": "the same display case now open with the necklace suddenly missing",
        "empty_case_aftermath": "the same open display case as the theft shock ripples through the room",
        "necklace_access": "the attendant opening controlled access to the signature necklace display",
        "security_system": "the boutique security layer controlling access to the room",
        "luxury_establishing": "the same protected luxury boutique environment centered on the display architecture and jewel-security system",
        "delayed_reaction": "the room still trying to understand the attack a moment too late",
        "operator_exit": "the operators already slipping beyond the boutique while the reaction lags behind",
        "historical_context": "Tokyo as a controlled night-time urban system connected to the heist",
        "institutional_realization": "the first institutional realization that the system is already late",
        "system_delay": "the slower institutional mechanism trying to understand a faster crime",
        "identity_reveal": "the emergence of the Pink Panthers identity through recurring jewel-theft evidence",
        "myth_rejection": "the stripped-down reality behind the Pink Panthers myth",
        "menace_under_myth": "the darker criminal reality hiding behind the almost comic anecdote",
        "object_evidence": "a cream jar hiding a jewel as a concrete piece of criminal evidence",
        "network_introduction": "a disciplined transnational organization expanding beyond a single robbery into a coordinated network",
        "investigative_mechanism": "the hidden operational mechanism behind the Pink Panthers network",
        "investigative_bridge": "a continuity-safe transition image with no primary narrative payload",
    }
    primary_subject = primary_subject_map.get(shot_role, "the recurring documentary subject")
    if bundle["theme_hint"] == "luxury_jewel_heist_documentary" and primary_subject in ABSTRACT_PRIMARY_SUBJECTS:
        raise ValueError(f"Scene {scene['scene_id']} resolved to an abstract primary subject")

    environment = resolve_environment(active_ids, location_map, shot_role, bundle["theme_hint"])

    details = []
    if "lead_operator" in active_ids:
        details.append("Keep the lead operator visually identical in suit, posture, grooming, and silhouette.")
    if "support_operator" in active_ids:
        details.append("Keep the support operator visually identical in coat, hairstyle, jewelry, and silhouette.")
    if "boutique_attendant" in active_ids:
        details.append("Keep the boutique attendant visually identical in uniform, bun hairstyle, scarf, and professional posture.")
    if "security_guard" in active_ids:
        details.append("Keep the security guard visually identical in navy suit, shaved head, and earpiece.")
    if "display_case" in active_ids and "display_case" in object_map:
        details.append(object_map["display_case"]["profile"])
    if "signature_necklace" in active_ids and "signature_necklace" in object_map:
        details.append(object_map["signature_necklace"]["profile"])
    if "cream_jar_evidence" in active_ids and "cream_jar_evidence" in object_map:
        details.append(object_map["cream_jar_evidence"]["profile"])
    if "route_fragments" in active_ids and "route_fragments" in object_map:
        details.append(object_map["route_fragments"]["profile"])
    if bundle["recurring_motifs"]:
        details.append("Recurring motifs: " + ", ".join(bundle["recurring_motifs"][:4]))

    prompt_lines = [
        "Create a premium cinematic documentary still in 16:9.",
        "",
        f"Scene meaning: {blueprint['scene_meaning']}",
        f"Visual: Show {primary_subject} in a way that reflects {blueprint['visual_goal'].lower()} and feels like one unified documentary film rather than a random standalone image.",
        f"Main subject: {primary_subject}",
        "Character continuity:",
    ]
    prompt_lines.extend(profiles or ["- Reuse the same recurring subject and object design across the sequence."])
    prompt_lines.extend(
        [
            f"Action without speech: {blueprint['action']}",
            f"Environment: {environment}",
            f"Composition: {blueprint['composition']}",
            f"Angle: {blueprint['angle']}",
            "Camera: realistic documentary photography, natural lens perspective, cinematic framing, realistic depth of field",
            f"Lighting: {blueprint['lighting']}",
            f"Atmosphere: {blueprint['atmosphere']}",
            "Important details:",
        ]
    )
    prompt_lines.extend(f"- {item}" for item in details[:7] or ["- Maintain realistic physical detail and layered depth."])
    prompt_lines.extend(
        [
            f"Style: {STYLE_SUMMARY}",
            "Restrictions: no real-person names, no text, no subtitles, no logos, no watermark, no fake UI, no distorted hands, no plastic skin, no generic stock photo aesthetic, no random replacement characters",
        ]
    )
    prompt = "\n".join(prompt_lines)

    return {
        "shot_role": shot_role,
        "primary_subject": primary_subject,
        "environment": environment,
        "composition": blueprint["composition"],
        "angle": blueprint["angle"],
        "lighting": blueprint["lighting"],
        "atmosphere": blueprint["atmosphere"],
        "visual_goal": blueprint["visual_goal"],
        "prompt": prompt,
        "active_entity_ids": active_ids,
        "continuity_cast": profiles,
        "continuity_focus": scene_entry["continuity_focus"],
        "semantic_descriptor": descriptor,
    }


def build_beat_report(scenes: list[dict]) -> str:
    lines = ["# Beat Extraction Report", ""]
    for scene in scenes:
        lines.extend(
            [
                f"Scene {scene['shot_index']} ({scene['scene_id']})",
                f"Timing: {scene['start']:.3f}-{scene['end']:.3f}s",
                f"Event type: {scene.get('event_type', '')}",
                f"Part semantic role: {scene.get('part_semantic_role', '')}",
                f"Semantic action: {scene.get('semantic_action', '')}",
                f"Visual function: {scene.get('visual_function', '')}",
                f"Visual strategy: {scene.get('visual_strategy', '')}",
                f"Role confidence: {scene.get('role_confidence', 0):.2f}",
                f"Fallback reason: {scene.get('fallback_reason', '') or 'none'}",
                f"Voice text: {scene.get('voice_text', '')}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def run_prompt_package_qa(items: list[dict], theme_hint: str) -> dict:
    issues = []
    warnings = []
    for item in items:
        if item["primary_subject"].strip().lower() in ABSTRACT_PRIMARY_SUBJECTS:
            issues.append(f"{item['scene_id']}: abstract primary_subject is not allowed")
        if item["semantic_descriptor"]["event_clarity_required"] and "bridge" in item["shot_role"]:
            issues.append(f"{item['scene_id']}: event_clarity_required scene cannot use bridge role")

    for start in range(max(0, len(items) - 2)):
        trio = items[start : start + 3]
        same_environment = len({item["environment"] for item in trio}) == 1
        same_subject = len({item["primary_subject"] for item in trio}) == 1
        different_actions = len({item["semantic_descriptor"]["semantic_action"] for item in trio}) > 1
        if same_environment and same_subject and different_actions:
            issues.append(
                f"{trio[0]['scene_id']}..{trio[-1]['scene_id']}: same environment and primary subject repeated across distinct semantic actions"
            )

    streak_role = None
    streak_count = 0
    for item in items:
        if item["shot_role"] == streak_role:
            streak_count += 1
        else:
            streak_role = item["shot_role"]
            streak_count = 1
        if streak_count >= 4:
            warnings.append(f"{item['scene_id']}: shot_role streak reached {streak_count} for {streak_role}")

    status = "passed" if not issues else "failed"
    return {"status": status, "issues": issues, "warnings": warnings}
