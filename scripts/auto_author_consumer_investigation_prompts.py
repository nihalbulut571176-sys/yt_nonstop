import argparse
import re
from pathlib import Path

from project_pipeline_utils import load_json, load_project, save_json, save_project


STYLE_SUMMARY = (
    "Realistic cinematic investigative documentary still, grounded physical detail, "
    "strong subject readability, atmospheric but believable lighting, 16:9 composition, no text."
)

NEGATIVE_PROMPT = (
    "text, subtitles, watermark, logo, infographic layout, split screen, cartoon style, "
    "surreal symbolism, floating UI overlays, distorted anatomy, unreadable labels"
)


ROLE_RULES = [
    (
        "supermarket_choice",
        {
            "магазин", "супермаркет", "тележк", "полк", "ценник", "скидк", "упаковк", "выбор", "корзин",
            "supermarket", "aisle", "shelf", "price", "discount", "packaging", "cart",
        },
    ),
    (
        "shopper_pressure",
        {
            "рабоч", "дня", "ребенок", "карман", "телефон", "спеш", "устал", "контрол", "эконом", "дешев",
            "shopper", "tired", "phone", "child", "stress", "budget", "cheap",
        },
    ),
    (
        "brand_manipulation",
        {
            "бренд", "натуральн", "эмблем", "упаковк", "привычк", "маркетинг", "витрин", "дизайн",
            "brand", "natural", "marketing", "habit", "design", "label", "packaging",
        },
    ),
    (
        "supplier_pressure",
        {
            "поставщик", "контракт", "ритейлер", "производ", "фермер", "закупоч", "цену", "давить",
            "supplier", "contract", "retailer", "producer", "farmer", "purchase", "pressure",
        },
    ),
    (
        "water_extraction",
        {
            "бутылк", "воды", "скважин", "литр", "вода", "источник", "напит", "giant", "beverage",
            "water", "well", "bottle", "aquifer", "spring",
        },
    ),
    (
        "food_lab",
        {
            "вкус", "лаборатор", "зависим", "сахар", "соль", "жир", "формул", "снек", "газировк",
            "flavor", "lab", "addiction", "sugar", "salt", "fat", "snack", "soda",
        },
    ),
    (
        "digital_nudge",
        {
            "киоск", "цифров", "экран", "интерфейс", "подталкив", "купить", "приложен", "алгоритм",
            "kiosk", "digital", "screen", "interface", "app", "algorithm", "upsell",
        },
    ),
    (
        "hidden_cost",
        {
            "здоров", "земл", "будущ", "дешевизн", "заплат", "экологи", "цена", "черный", "ящик",
            "health", "soil", "future", "cost", "hidden", "black", "box", "externality",
        },
    ),
    (
        "call_to_awareness",
        {
            "лайк", "выпуск", "осознан", "потребител", "слеп", "видеть", "поним", "границ",
            "episode", "awareness", "consumer", "understand", "see", "blind",
        },
    ),
]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-zА-Яа-яЁёÀ-ÿÄÖÜäöüß']+", text.lower())


def matches_stem(token: str, stems: set[str]) -> bool:
    return any(token.startswith(stem) for stem in stems)


def infer_role(text: str, shot_index: int, scene_count: int) -> str:
    tokens = tokenize(text)
    for role, stems in ROLE_RULES:
        if any(matches_stem(token, stems) for token in tokens):
            return role
    if shot_index <= 12:
        return "supermarket_choice"
    if shot_index >= max(1, scene_count - 18):
        return "call_to_awareness"
    return "hidden_cost"


def role_details(role: str) -> tuple[str, str, str, str, str, str]:
    mapping = {
        "supermarket_choice": (
            "show that consumer choice is being shaped before the shopper consciously decides",
            "a supermarket aisle with pricing cues, shelf layout, and attention-grabbing packaging",
            "a grounded European supermarket interior",
            "a shopper hesitating while the shelf design silently guides the decision",
            "eye-level observational documentary shot",
            "cool retail light with realistic contrast",
        ),
        "shopper_pressure": (
            "translate everyday fatigue and overload into a vulnerable buying moment",
            "an overstimulated shopper navigating a grocery aisle under time pressure",
            "a crowded supermarket near checkout or a discount section",
            "the shopper moving quickly while juggling fatigue, phone distraction, and family pressure",
            "handheld-feeling medium documentary shot",
            "mixed store light with slightly tense contrast",
        ),
        "brand_manipulation": (
            "show how branding aesthetics manufacture trust and familiarity",
            "packaging, labels, and branded food products competing for attention on a shelf",
            "a tightly framed supermarket shelf or endcap display",
            "bright labels, color-coded discounts, and repeated brand signals dominating the viewer's attention",
            "compressed close documentary shot",
            "clean commercial light with sharp readable surfaces",
        ),
        "supplier_pressure": (
            "make supply-chain power visible through negotiations, contracts, and squeezed producers",
            "a producer, farm, or warehouse context under retailer price pressure",
            "a loading dock, farm office, or industrial backroom tied to food distribution",
            "documents, pallets, produce, and a tense business interaction revealing asymmetric power",
            "restrained investigative medium-wide shot",
            "neutral industrial daylight",
        ),
        "water_extraction": (
            "connect cheap bottled consumption to hidden extraction and depletion",
            "bottled water production or groundwater extraction infrastructure",
            "a bottling plant, well site, or stacked water display linked to supply extraction",
            "water leaving the ground or entering plastic bottles at industrial scale",
            "clean environmental documentary shot",
            "crisp daylight with reflective highlights",
        ),
        "food_lab": (
            "show engineered taste and dependency as a deliberate industrial process",
            "a food lab, formulation bench, or processed snack production detail",
            "a research kitchen, test lab, or food-processing workstation",
            "ingredients, samples, and precision tools shaping flavor for repeat consumption",
            "precise close-up investigative shot",
            "controlled lab light",
        ),
        "digital_nudge": (
            "show the interface as a sales machine that nudges the buyer toward more spending",
            "a self-service kiosk, app, or checkout screen steering purchase behavior",
            "a supermarket kiosk area or a phone-driven ordering moment",
            "buttons, offers, and layout logic pushing the user toward a larger basket",
            "over-the-shoulder interface documentary shot",
            "glowing screen light balanced with realistic surroundings",
        ),
        "hidden_cost": (
            "visualize the invisible cost hidden behind cheap food and apparent convenience",
            "the unseen system behind low prices: farms, factories, packaging waste, transport, or exhausted land",
            "a back-of-house industrial or agricultural setting connected to retail food",
            "material consequences accumulating outside the polished storefront",
            "symbolically concrete investigative wide shot",
            "muted natural or industrial light",
        ),
        "call_to_awareness": (
            "end on clarity and awareness rather than passive consumption",
            "a reflective consumer moment that suggests recognition of the system behind cheap food",
            "a quiet supermarket exit, kitchen table, or stripped-back retail setting",
            "the subject pausing, reconsidering, and seeing the food system more clearly",
            "calm closing documentary shot",
            "soft realistic evening light",
        ),
    }
    return mapping[role]


def summarize_excerpt(text: str, limit_words: int = 14) -> str:
    words = normalize_text(text).split()
    return " ".join(words[:limit_words]).strip(" ,.;:-")


def build_visual_bible(project: dict) -> dict:
    return {
        "project_id": project["project_id"],
        "main_subject": "the hidden system behind cheap supermarket food",
        "subject_type": "consumer_investigation",
        "visual_world": (
            "A realistic investigative documentary about how supermarkets, brands, suppliers, and food interfaces shape "
            "consumer choice and hide the real cost of cheap food. Keep scenes concrete, human-readable, and physically grounded."
        ),
        "style_summary": STYLE_SUMMARY,
        "prompt_language": "English",
        "recurring_motifs": [
            "supermarket shelves",
            "discount signage without readable text",
            "food packaging as manipulation",
            "supplier pressure",
            "industrial food systems",
            "bottled water extraction",
            "lab-designed taste",
            "digital retail nudges",
        ],
        "continuity_rules": [
            "Keep the project inside one coherent modern European consumer-food documentary world.",
            "Translate abstract claims into concrete scenes, mechanisms, or consequences.",
            "When a sentence is split into multiple shots, keep the same beat but vary framing or emphasis.",
            "Do not turn the video into abstract symbolism when a real-world scene can communicate the same idea better.",
        ],
        "forbidden_mistakes": [
            "Do not put readable text or fake subtitles inside the frame.",
            "Do not use random wildlife, fantasy, or off-topic stock imagery.",
            "Do not make every scene just a generic supermarket aisle.",
            "Do not lose the human, economic, or environmental stakes behind the narration.",
        ],
        "scene_role_taxonomy": [role for role, _ in ROLE_RULES],
        "visual_blocks": [
            "consumer choice illusion",
            "shopper vulnerability",
            "brand and shelf engineering",
            "supplier and farmer pressure",
            "industrial externalities",
            "digital nudges and closing awareness",
        ],
        "global_negative_prompt": NEGATIVE_PROMPT.split(", "),
    }


def build_prompt(record: dict, scene_count: int) -> dict:
    scene_id = record["scene_id"]
    shot_index = int(record["shot_index"])
    voice_text = normalize_text(str(record.get("voice_text", "")))
    role = infer_role(voice_text, shot_index, scene_count)
    goal, subject, environment, action, camera, lighting = role_details(role)
    excerpt = summarize_excerpt(voice_text)

    part_index = int(record.get("part_index") or 1)
    parts_total = int(record.get("parts_total") or 1)
    variation_note = ""
    if parts_total > 1:
        variation_note = f"Part {part_index} of {parts_total} for the same narration beat."
        if part_index > 1:
            camera = "tighter continuity angle on the same beat"

    mood = {
        "supermarket_choice": "subtle manipulation, polished normality",
        "shopper_pressure": "fatigue, urgency, overstimulation",
        "brand_manipulation": "seductive, engineered trust",
        "supplier_pressure": "asymmetric power, quiet pressure",
        "water_extraction": "clean surface, hidden depletion",
        "food_lab": "clinical precision, manufactured craving",
        "digital_nudge": "frictionless control, algorithmic persuasion",
        "hidden_cost": "uneasy clarity, concealed consequence",
        "call_to_awareness": "reflective, lucid, resolved",
    }[role]

    what_is_in_frame = (
        f"{subject}, in {environment}, with {action}. The frame should make the narrated mechanism visible without relying on on-screen text."
    )

    final_prompt = (
        f"{STYLE_SUMMARY} Show {subject} in {environment}. "
        f"Action: {action}. Camera: {camera}. Lighting: {lighting}. Mood: {mood}. "
        f"Scene beat: {excerpt}. "
        f"Direction: {goal}. Keep it concrete, contemporary, and grounded in a supermarket or food-system investigation. "
        f"If the narration is abstract, translate it into a visible mechanism or consequence rather than symbolism. "
        f"Negative prompt: {NEGATIVE_PROMPT}."
    )

    return {
        "scene_id": scene_id,
        "visual_goal": goal,
        "shot_role": role,
        "primary_subject": subject,
        "secondary_subjects": [],
        "what_is_in_frame": what_is_in_frame,
        "camera": camera,
        "composition": "keep the causal mechanism legible and the frame visually uncluttered",
        "lighting": lighting,
        "mood": mood,
        "continuity_notes": "Preserve continuity with neighboring scenes and keep the investigation inside one coherent consumer-food world.",
        "negative_prompt": NEGATIVE_PROMPT,
        "final_prompt": final_prompt,
        "scene_importance": "hero" if shot_index <= 12 or role in {"supplier_pressure", "water_extraction", "food_lab", "digital_nudge"} else "supporting",
        "shot_id": f"shot_{shot_index:04d}",
        "source_shot_id": f"shot_{max(1, shot_index - 1):04d}",
        "generation_mode": "unique",
        "variation_note": variation_note or None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    scene_context_pack_path = Path(project["prompts"]["scene_context_pack_path"])
    visual_bible_path = Path(project["prompts"]["visual_bible_path"])
    drafts_path = Path(project["prompts"]["llm_prompt_drafts_path"])

    records = load_json(scene_context_pack_path)
    scene_count = len(records)
    visual_bible = build_visual_bible(project)
    drafts = [build_prompt(record, scene_count) for record in records]

    save_json(visual_bible_path, visual_bible)
    save_json(drafts_path, drafts)

    project["prompts"]["visual_bible_path"] = str(visual_bible_path)
    project["prompts"]["llm_prompt_drafts_path"] = str(drafts_path)
    save_project(project_json, project)

    print(visual_bible_path)
    print(drafts_path)


if __name__ == "__main__":
    main()
