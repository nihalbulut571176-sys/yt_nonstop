import argparse
import re
from collections import Counter
from pathlib import Path

from project_pipeline_utils import load_json, load_project, save_json, save_project
from prompt_safety import lint_prompt_observability


STOPWORDS = {
    "de": {
        "der", "die", "das", "und", "ein", "eine", "ist", "im", "in", "auf", "mit", "zu", "von", "den", "dem",
        "des", "fuer", "für", "als", "auch", "an", "am", "aus", "wie", "nicht", "nur", "wenn", "dass", "sich",
        "sein", "ihre", "ihren", "oder", "bei", "durch", "ueber", "über", "unter", "wild", "natur",
    },
    "en": {
        "the", "and", "a", "an", "in", "on", "with", "to", "of", "for", "from", "that", "this", "these", "those",
        "into", "over", "under", "through", "about", "wild", "nature",
    },
    "ru": {
        "это", "как", "что", "для", "она", "они", "его", "ее", "или", "над", "под", "так", "при", "про", "только",
    },
}


THEME_KEYWORDS = {
    "nature_macro": {
        "maikaefer", "maikäfer", "mai", "käfer", "kaefer", "beetle", "insect", "larva", "forest", "tree", "leaf",
        "wildlife", "wald", "boden", "natur", "tier", "ast", "laub", "wiese", "sun", "erde",
    },
    "tech_investigation": {
        "server", "hacker", "telegram", "darknet", "network", "phone", "screen", "code", "database", "chat",
    },
}


STYLE_PRESETS = {
    "nature_macro": {
        "style_name": "cinematic-macro-nature-documentary",
        "summary": "Ultra-realistic cinematic nature documentary style, macro wildlife photography, natural light, rich organic textures, shallow depth of field, atmospheric European forest mood, 16:9 composition, no text.",
        "negative_prompt": "text, watermark, logo, fantasy, cartoon, unrelated animals, humans, random wildlife, duplicate beetles, blurry anatomy",
    },
    "tech_investigation": {
        "style_name": "cinematic-tech-documentary",
        "summary": "Realistic cinematic investigative documentary style, moody contrast, precise details, clean composition, grounded realism, 16:9 frame, no text overlay.",
        "negative_prompt": "text, subtitles, watermark, logo, collage, split screen, cartoon style, distorted hands, blurry screen",
    },
    "general_documentary": {
        "style_name": "cinematic-realistic-documentary",
        "summary": "Realistic cinematic documentary still, grounded composition, natural lighting, rich detail, photographic realism, 16:9 aspect, no text.",
        "negative_prompt": "text, subtitles, watermark, logo, collage, split screen, low detail, deformed anatomy, unrelated animals",
    },
}


PREDATOR_TERMS = {
    "bird", "birds", "bat", "bats", "hedgehog", "hedgehogs", "mole", "moles", "ant", "ants",
    "predatory", "predator", "predators", "vogel", "vögel", "fledermäuse", "fledermaus",
    "igel", "maulwürfe", "maulwurf", "ameisen",
}

ANATOMY_TERMS = {
    "antenna": "cockchafer antennae",
    "antennae": "cockchafer antennae",
    "fühler": "cockchafer antennae",
    "fuehler": "cockchafer antennae",
    "wing": "cockchafer wings and elytra",
    "wings": "cockchafer wings and elytra",
    "deckflügel": "cockchafer elytra and wings",
    "deckfluegel": "cockchafer elytra and wings",
    "krallen": "cockchafer claws and hooked leg segments",
    "kralle": "cockchafer claws and hooked leg segments",
    "claw": "cockchafer claws and hooked leg segments",
    "claws": "cockchafer claws and hooked leg segments",
    "fuß": "cockchafer leg and gripping foot anatomy",
    "fuss": "cockchafer leg and gripping foot anatomy",
    "bein": "cockchafer leg anatomy",
    "beine": "cockchafer leg anatomy",
    "body": "cockchafer body anatomy",
    "körper": "cockchafer body anatomy",
    "koerper": "cockchafer body anatomy",
    "larve": "cockchafer larva underground",
    "grub": "cockchafer larva underground",
}


SCENE_ARCHETYPES = {
    "atmospheric_intro": {
        "label": "atmospheric introduction",
        "shot_pool": ["wide atmospheric nature shot", "moody twilight forest shot", "close cinematic habitat shot"],
        "instruction": "Use anticipation, season, weather, forest mood, grass, leaves, bark, and evening atmosphere. The beetle may be small, implied, emerging, or just about to appear.",
    },
    "adult_habitat": {
        "label": "adult beetle habitat",
        "shot_pool": ["intimate documentary close shot", "detailed habitat close-up", "low-angle macro shot"],
        "instruction": "Show the adult beetle clearly, but vary perch, angle, scale, background, and surrounding vegetation.",
    },
    "adult_flight": {
        "label": "flight and movement",
        "shot_pool": ["dynamic twilight flight shot", "cinematic takeoff close-up", "mid-air documentary shot"],
        "instruction": "Show flight energy, wing deployment, dusk atmosphere, buzzing movement, and believable motion cues instead of a static resting pose.",
    },
    "mating_search": {
        "label": "mate search",
        "shot_pool": ["tree-canopy search shot", "scent-tracking documentary shot", "close interaction shot"],
        "instruction": "The scene may include male and female beetles, tree crowns, branches, leaves, and scent-tracking behavior in dusk light.",
    },
    "predator_threat": {
        "label": "predators and danger",
        "shot_pool": ["tense wildlife documentary shot", "threat-focused environmental shot", "ground-level danger shot"],
        "instruction": "Predators may be visible only because the narration calls for them. The image must still clearly belong to the cockchafer story, not become a random animal portrait.",
    },
    "underground_life": {
        "label": "underground life",
        "shot_pool": ["cross-section soil documentary shot", "macro underground chamber shot", "root-zone close-up"],
        "instruction": "Show soil layers, roots, darkness, moisture, eggs, tunnels, and larval life below ground. Adult beetles do not need to appear.",
    },
    "metamorphosis": {
        "label": "metamorphosis",
        "shot_pool": ["transformational underground close-up", "pupal chamber documentary shot", "quiet rebirth macro shot"],
        "instruction": "Lean into transformation, fragility, pale fresh body tones, and the drama of becoming underground.",
    },
    "anatomy_macro": {
        "label": "anatomy and science detail",
        "shot_pool": ["extreme macro anatomy shot", "precision scientific close-up", "texture-rich detail insert"],
        "instruction": "Focus tightly on the described body part and its function. Avoid generic full-body repetition.",
    },
    "ecology_damage": {
        "label": "ecology and plant impact",
        "shot_pool": ["root damage documentary shot", "field-and-garden environmental shot", "close ecological evidence shot"],
        "instruction": "Show roots, leaves, crops, forest, or garden impact when the narration discusses damage or ecological effect.",
    },
    "historical_human": {
        "label": "historical human context",
        "shot_pool": ["19th-century rural scene", "historical documentary tableau", "archival-feeling naturalistic scene"],
        "instruction": "Human presence is allowed here because the narration shifts into history. Keep it grounded, rural, and documentary-like.",
    },
    "nostalgia_memory": {
        "label": "nostalgia and memory",
        "shot_pool": ["warm nostalgic evening shot", "memory-like close documentary shot", "golden-hour atmospheric scene"],
        "instruction": "The beetle does not always need to dominate the frame. Atmosphere, hand, grass, twilight, and lived memory can carry the meaning.",
    },
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-zÀ-ÿÄÖÜäöüß]+", text.lower())


def infer_theme(scene_texts: list[str]) -> str:
    tokens: list[str] = []
    for text in scene_texts:
        tokens.extend(tokenize(text))
    token_set = set(tokens)
    scores = {theme: len(token_set & keywords) for theme, keywords in THEME_KEYWORDS.items()}
    best_theme = max(scores, key=scores.get) if scores else "general_documentary"
    return best_theme if scores.get(best_theme, 0) > 0 else "general_documentary"


def infer_keywords(scene_texts: list[str], language: str, limit: int = 8) -> list[str]:
    stopwords = STOPWORDS.get(language, STOPWORDS["en"])
    counts: Counter[str] = Counter()
    for text in scene_texts:
        for token in tokenize(text):
            if len(token) < 3 or token in stopwords:
                continue
            counts[token] += 1
    return [token for token, _ in counts.most_common(limit)]


def summarize_excerpt(text: str, max_words: int = 12) -> str:
    cleaned = normalize_text(text)
    words = cleaned.split()
    return " ".join(words[:max_words]).strip(" ,.;:-")


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


def detect_main_subject(source_text: str, scene_texts: list[str], theme: str) -> dict[str, str]:
    corpus = f"{source_text}\n" + "\n".join(scene_texts)
    lower = corpus.lower()
    if theme == "nature_macro" and any(term in lower for term in ["maikäfer", "maikaefer", "may beetle", "cockchafer"]):
        return {
            "subject_short": "cockchafer beetle",
            "subject_full": "cockchafer beetle (May beetle, Maikäfer)",
            "project_focus": "This video is about the cockchafer beetle and its life cycle.",
        }
    if theme == "nature_macro":
        return {
            "subject_short": "featured insect",
            "subject_full": "the featured insect species from the narration",
            "project_focus": "This video is about one specific insect species and its life cycle.",
        }
    return {
        "subject_short": "main subject",
        "subject_full": "the main documentary subject of this video",
        "project_focus": "This video follows one central subject and should remain visually consistent.",
    }


def build_master_prompt(subject: dict[str, str], theme: str) -> str:
    if theme == "nature_macro":
        return (
            "One coherent cinematic European nature documentary world. "
            f"Stay faithful to the life cycle and story of the {subject['subject_short']}. "
            "Vary scene role and composition. Avoid repeating the same generic beetle-on-branch shot."
        )
    return (
        f"{subject['project_focus']} Keep {subject['subject_full']} visually central and consistent across scenes. "
        "Do not introduce unrelated subjects that are not motivated by the narration."
    )


def classify_scene_archetype(scene_text: str, index: int, total: int) -> str:
    tokens = set(tokenize(scene_text))
    lower = normalize_text(scene_text).lower()

    historical_terms = {"jahrhundert", "nineteenth", "historisch", "suppe", "korb", "sammler", "dorf", "bauern"}
    nostalgia_terms = {"kindheit", "erinnerung", "erinnerungen", "maiabend", "warmen", "wiedersehen", "nostalgie", "hand", "gras"}
    metamorphosis_terms = {"puppe", "puppa", "metamorphose", "verwandelt", "verwandlung", "zweites", "geboren"}
    underground_terms = {"erde", "boden", "wurzel", "wurzeln", "soil", "root", "roots", "egg", "eggs", "ei", "eier", "larve", "larven", "kammer", "tunnel", "unterirdisch", "underground"}
    mating_terms = {"weibchen", "männchen", "maennchen", "paar", "partner", "partnerin", "baumkronen", "baumkrone", "duft", "spur", "suchen"}
    flight_terms = {"flug", "fliegen", "fliegt", "abhebt", "luft", "brummen", "brummt", "flügel", "fluegel", "deckflügel", "deckfluegel"}
    ecology_terms = {"schaden", "schädling", "schaedling", "feld", "garten", "kulturpflanzen", "wurzelfraß", "wurzelfrass", "crop", "damage"}

    if tokens & historical_terms or "maikäfersuppe" in lower or "maikaefersuppe" in lower:
        return "historical_human"
    if tokens & nostalgia_terms and index > int(total * 0.75):
        return "nostalgia_memory"
    if index == 1:
        return "adult_flight"
    if index == 2:
        return "metamorphosis"
    if tokens & metamorphosis_terms:
        return "metamorphosis"
    if tokens & underground_terms:
        return "underground_life"
    if any(term in tokens for term in PREDATOR_TERMS):
        return "predator_threat"
    if any(term in tokens for term in ANATOMY_TERMS):
        return "anatomy_macro"
    if tokens & mating_terms:
        return "mating_search"
    if tokens & flight_terms:
        return "adult_flight"
    if tokens & ecology_terms:
        return "ecology_damage"
    if index <= max(10, int(total * 0.08)):
        return "atmospheric_intro"
    if index >= int(total * 0.9):
        return "nostalgia_memory"
    return "adult_habitat"


def detect_scene_subject(scene_text: str, subject: dict[str, str], archetype: str) -> str:
    tokens = set(tokenize(scene_text))
    if archetype == "underground_life":
        return "cockchafer larva, eggs, roots, and underground chambers"
    if archetype == "metamorphosis":
        return "cockchafer pupa and transformation underground"
    if archetype == "historical_human":
        return "a historical rural scene connected to cockchafer swarms"
    if archetype == "nostalgia_memory":
        return "a nostalgic May evening memory connected to the cockchafer"
    if archetype == "predator_threat":
        return f"{subject['subject_short']} under threat from natural predators"
    if archetype == "adult_flight":
        return f"the adult {subject['subject_short']} in flight"
    if archetype == "mating_search":
        return f"the adult {subject['subject_short']} searching for a mate"
    if archetype == "ecology_damage":
        return "the ecological trace of cockchafer life in roots, plants, or fields"
    if archetype == "atmospheric_intro":
        return "the spring habitat and atmosphere surrounding cockchafer emergence"
    if archetype == "adult_habitat":
        return f"adult {subject['subject_short']} in habitat"
    if archetype == "mating_search":
        if "weibchen" in tokens:
            return "female cockchafer feeding on fresh leaves"
        if "männchen" in tokens or "maennchen" in tokens:
            return "male cockchafer with opened fan-like antennae"
    if archetype == "anatomy_macro":
        for token, mapped in ANATOMY_TERMS.items():
            if token in tokens:
                return mapped
    return f"adult {subject['subject_short']}"


def build_scene_constraint(scene_text: str, subject: dict[str, str], archetype: str) -> str:
    tokens = set(tokenize(scene_text))
    if archetype == "atmospheric_intro":
        return "Prioritize anticipation, environment, and seasonal mood over a repetitive hero close-up."
    if archetype == "adult_habitat":
        return f"Keep {subject['subject_short']} identifiable, but vary angle, scale, perch, and surrounding vegetation."
    if archetype == "adult_flight":
        return "Show believable takeoff, open wing cases, or buzzing motion instead of a static perched pose."
    if archetype == "mating_search":
        return "Make the scene about searching, tracking, tree crowns, scent, and proximity to a mate, not just a random resting beetle."
    if archetype == "predator_threat":
        return f"Predators may appear only because the narration calls for them. Keep the shot clearly tied to {subject['subject_short']} and its survival."
    if archetype == "underground_life":
        return "Use soil, roots, darkness, eggs, tunnels, and larval anatomy. Do not default back to an adult beetle on a leaf."
    if archetype == "metamorphosis":
        return "Show pupa, developing adult form, or emergence chamber with a strong sense of transformation."
    if archetype == "anatomy_macro" or any(term in tokens for term in ANATOMY_TERMS):
        return "Make this an informative macro-scientific visual, not another generic full-body beetle portrait."
    if archetype == "ecology_damage":
        return "The scene may emphasize roots, leaves, field or garden impact. The beetle may be present directly or implied through the damage."
    if archetype == "historical_human":
        return "Keep it historically grounded, rural, and documentary-like. No fantasy styling or modern props."
    if archetype == "nostalgia_memory":
        return "Favor emotion, light, season, memory, and lived experience. The beetle may be secondary if the memory remains clearly tied to it."
    return f"Keep the shot connected to {subject['subject_short']} and avoid falling back to a repetitive default composition."


def make_visual_goal(excerpt: str, subject_label: str, archetype: str) -> str:
    return f"Show {subject_label} as a {SCENE_ARCHETYPES[archetype]['label']} scene, focused on this narrated idea: {excerpt}."


def pick_environment(archetype: str) -> str:
    mapping = {
        "atmospheric_intro": "spring forest edge at dusk",
        "adult_habitat": "European forest leaves, bark, or grass",
        "adult_flight": "twilight air above spring grass or leaves",
        "mating_search": "tree canopy and fresh spring leaves at dusk",
        "predator_threat": "forest edge, air, or ground-level danger zone",
        "underground_life": "moist soil, roots, and underground chambers",
        "metamorphosis": "quiet underground pupal chamber",
        "anatomy_macro": "neutral natural macro setting with real textures",
        "ecology_damage": "roots, field, garden, or damaged vegetation",
        "historical_human": "19th-century rural Central European setting",
        "nostalgia_memory": "warm May evening, grass, hand, and twilight atmosphere",
    }
    return mapping[archetype]


def pick_camera(shot_label: str) -> str:
    return shot_label


def subject_action(scene_text: str, archetype: str, subject_label: str) -> str:
    text = normalize_text(scene_text).lower()
    if archetype == "adult_flight":
        return "preparing to take off with wing cases opening"
    if archetype == "mating_search":
        if "weibchen" in text:
            return "feeding quietly on fresh leaves"
        if "männchen" in text or "maennchen" in text:
            return "searching through dusk air with opened fan-like antennae"
        return "moving through the tree canopy in search of a mate"
    if archetype == "underground_life":
        if "ei" in text or "eier" in text:
            return "resting in the soil near roots"
        return "living below ground among roots and dark soil"
    if archetype == "metamorphosis":
        return "transforming underground between larva, pupa, and adult form"
    if archetype == "predator_threat":
        return "caught in a dangerous moment within the food chain"
    if archetype == "anatomy_macro":
        return f"showing the exact structure of {subject_label}"
    if archetype == "ecology_damage":
        return "revealing plant impact through roots or feeding traces"
    if archetype == "historical_human":
        return "appearing within a historically grounded human context"
    if archetype == "nostalgia_memory":
        return "appearing inside a warm nostalgic May-evening memory"
    if archetype == "atmospheric_intro":
        return "hinted at within the first signs of spring and evening emergence"
    return "shown in a natural documentary moment"


def make_prompt(
    excerpt: str,
    scene_text: str,
    archetype: str,
    shot_label: str,
    subject_label: str,
    master_prompt: str,
    scene_constraint: str,
    style_summary: str,
    negative_prompt: str,
) -> str:
    environment = pick_environment(archetype)
    action = subject_action(scene_text, archetype, subject_label)
    camera = pick_camera(shot_label)
    return (
        f"Ultra-realistic cinematic documentary still of {subject_label}, {action}, in {environment}, "
        f"{camera}, natural light, rich organic textures, shallow depth of field, 16:9, no text. "
        f"Scene beat: {excerpt}. Direction: {scene_constraint} {master_prompt} "
        f"Negative prompt: {negative_prompt}."
    )


def describe_frame(subject_label: str, archetype: str, action: str, environment: str) -> str:
    return f"{subject_label} {action} in {environment}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    prompt_package_path = Path(project["prompts"]["prompt_package_path"])
    scene_plan_path = Path(project["scene_plan"]["scene_plan_path"])
    project_root = Path(project["meta"]["project_root"])
    style_guide_path = Path(project["prompts"].get("style_guide_path") or (project_root / "prompts" / "style_guide.json"))

    package = load_json(prompt_package_path)
    scene_plan = load_json(scene_plan_path)
    items = package.get("items", [])
    scene_texts = [str(item.get("voice_text", "")) for item in items if str(item.get("voice_text", "")).strip()]

    source_language = str(project["meta"].get("language", "auto")).lower()
    if source_language not in {"de", "en", "ru"}:
        source_language = "en"

    theme = infer_theme(scene_texts)
    preset = STYLE_PRESETS[theme]
    theme_keywords = infer_keywords(scene_texts, source_language)
    source_text = read_source_text(project)
    subject = detect_main_subject(source_text, scene_texts, theme)
    master_prompt = build_master_prompt(subject, theme)

    style_guide = {
        "project_id": project["project_id"],
        "source_language": project["meta"].get("language", "auto"),
        "prompt_language": project["prompts"]["prompt_language"],
        "theme": theme,
        "style_name": preset["style_name"],
        "style_summary": preset["summary"],
        "keywords": theme_keywords,
        "main_subject_short": subject["subject_short"],
        "main_subject_full": subject["subject_full"],
        "master_prompt": master_prompt,
        "negative_prompt": preset["negative_prompt"],
        "scene_archetypes": sorted(SCENE_ARCHETYPES.keys()),
    }
    style_guide_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(style_guide_path, style_guide)

    scene_map = {scene["scene_id"]: scene for scene in scene_plan.get("scenes", [])}
    archetype_counts: Counter[str] = Counter()
    total_items = len(items)

    for index, item in enumerate(items, start=1):
        scene_text = str(item.get("voice_text", "") or "documentary subject")
        excerpt = summarize_excerpt(scene_text)
        archetype = classify_scene_archetype(scene_text, index, total_items)
        archetype_counts[archetype] += 1
        shot_pool = SCENE_ARCHETYPES[archetype]["shot_pool"]
        shot_label = shot_pool[(archetype_counts[archetype] - 1) % len(shot_pool)]
        subject_label = detect_scene_subject(scene_text, subject, archetype)
        scene_constraint = build_scene_constraint(scene_text, subject, archetype)
        visual_goal = make_visual_goal(excerpt, subject_label, archetype)
        environment = pick_environment(archetype)
        action = subject_action(scene_text, archetype, subject_label)
        prompt = make_prompt(
            excerpt=excerpt,
            scene_text=scene_text,
            archetype=archetype,
            shot_label=shot_label,
            subject_label=subject_label,
            master_prompt=master_prompt,
            scene_constraint=scene_constraint,
            style_summary=preset["summary"],
            negative_prompt=preset["negative_prompt"],
        )
        what_is_in_frame = describe_frame(subject_label, archetype, action, environment)
        safety_warnings = lint_prompt_observability(
            prompt=prompt,
            primary_subject=subject_label,
            what_is_in_frame=what_is_in_frame,
        )

        item["visual_goal"] = visual_goal
        item["prompt"] = prompt
        item["scene_archetype"] = archetype
        item["primary_subject"] = subject_label
        item["what_is_in_frame"] = what_is_in_frame
        item["camera"] = shot_label
        item["composition"] = shot_label
        item["lighting"] = "natural light"
        item["mood"] = SCENE_ARCHETYPES[archetype]["label"]
        item["negative_prompt"] = preset["negative_prompt"]
        item["status"] = "drafted"
        item["notes"] = ["Auto-drafted from global master prompt and scene archetype logic"]
        if safety_warnings:
            item["notes"].append("Prompt safety review: " + " | ".join(safety_warnings))

        scene = scene_map.get(item["scene_id"])
        if scene:
            scene["visual_goal"] = visual_goal
            scene["prompt"] = prompt
            scene["scene_archetype"] = archetype
            scene["primary_subject"] = subject_label
            scene["what_is_in_frame"] = what_is_in_frame
            scene["camera"] = shot_label
            scene["lighting"] = "natural light"
            scene["mood"] = SCENE_ARCHETYPES[archetype]["label"]
            notes = [note for note in scene.get("notes", []) if note != "Prompt pending"]
            if "Prompt drafted automatically" not in notes:
                notes.append("Prompt drafted automatically")
            if safety_warnings:
                notes.append("Prompt safety review: " + " | ".join(safety_warnings))
            scene["notes"] = notes

    package["global_style_summary"] = preset["summary"]
    package["style_guide_path"] = str(style_guide_path)
    package["master_prompt"] = master_prompt
    package["main_subject_short"] = subject["subject_short"]
    package["scene_archetype_counts"] = dict(archetype_counts)
    save_json(prompt_package_path, package)
    save_json(scene_plan_path, scene_plan)

    review_path = Path(project["prompts"]["prompt_review_path"])
    review_lines = [
        f"Project: {project['project_id']}",
        f"Theme: {theme}",
        f"Style: {preset['style_name']}",
        f"Main subject: {subject['subject_full']}",
        f"Keywords: {', '.join(theme_keywords) if theme_keywords else 'none'}",
        "Master prompt:",
        master_prompt,
        "",
    ]
    for item in items:
        review_lines.extend(
            [
                f"Scene {item['shot_index']} ({item['scene_id']})",
                f"Archetype: {item.get('scene_archetype', 'unknown')}",
                f"Voice text: {item['voice_text']}",
                f"Visual goal: {item['visual_goal']}",
                f"What is in frame: {item.get('what_is_in_frame', '')}",
                f"Prompt: {item['prompt']}",
                f"Prompt safety warnings: {' | '.join(lint_prompt_observability(item['prompt'], item.get('primary_subject', ''), item.get('what_is_in_frame', ''))) or 'none'}",
                "",
            ]
        )
    review_path.write_text("\n".join(review_lines), encoding="utf-8")

    project["prompts"]["status"] = "drafted"
    project["prompts"]["style_guide_path"] = str(style_guide_path)
    project["prompts"]["global_style_summary"] = preset["summary"]
    project["current_stage"] = "publishing_package"
    save_project(project_json, project)

    print(style_guide_path)
    print(prompt_package_path)


if __name__ == "__main__":
    main()
