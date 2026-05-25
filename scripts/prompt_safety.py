import re
from typing import Any


ABSTRACT_TERMS = {
    "memory",
    "shared memory",
    "logic",
    "law",
    "laws",
    "destiny",
    "fate",
    "past itself",
    "returns from the past",
    "return from the past",
    "season itself",
    "evening itself",
    "world itself",
    "atmosphere rather than statement",
    "feels shared",
    "the whole season",
    "the whole logic",
    "entire logic",
    "many people",
}

OBSERVABLE_TERMS = {
    "cockchafer",
    "beetle",
    "insect",
    "larva",
    "pupa",
    "egg",
    "eggs",
    "soil",
    "root",
    "roots",
    "leaf",
    "leaves",
    "grass",
    "branch",
    "bark",
    "tree",
    "canopy",
    "wing",
    "wings",
    "elytra",
    "antenna",
    "antennae",
    "chamber",
    "tunnel",
    "meadow",
    "forest",
    "oak",
    "air",
    "ground",
    "dust",
    "pollen",
    "shadow",
    "swarm",
    "village",
    "field",
    "supermarket",
    "store",
    "shopper",
    "shelf",
    "aisle",
    "checkout",
    "cart",
    "basket",
    "packaging",
    "label",
    "bottle",
    "bottles",
    "kiosk",
    "screen",
    "phone",
    "factory",
    "warehouse",
    "loading dock",
    "pallet",
    "lab",
    "bench",
    "snack",
    "farmer",
    "producer",
    "contract",
    "discount",
    "price tag",
}

ENVIRONMENT_TERMS = {
    "soil",
    "ground",
    "root",
    "roots",
    "leaf",
    "leaves",
    "grass",
    "tree",
    "canopy",
    "forest",
    "woodland",
    "meadow",
    "field",
    "garden",
    "branch",
    "bark",
    "air",
    "dusk",
    "evening",
    "night",
    "surface",
    "underground",
    "chamber",
    "supermarket",
    "store",
    "aisle",
    "shelf",
    "checkout",
    "warehouse",
    "factory",
    "farm",
    "agricultural",
    "industrial",
    "storefront",
    "loading",
    "kiosk",
    "screen",
    "lab",
    "interior",
    "retail",
}

ACTION_TERMS = {
    "emerging",
    "emerge",
    "feeding",
    "flying",
    "facing",
    "opening",
    "searching",
    "resting",
    "clinging",
    "rising",
    "moving",
    "holding",
    "crossing",
    "transforming",
    "transform",
    "burrowing",
    "hovering",
    "crawling",
    "unfolding",
    "lifting",
    "vibrating",
    "buzzing",
    "paused",
    "poised",
    "hesitating",
    "shopping",
    "reaching",
    "grabbing",
    "scanning",
    "guiding",
    "juggling",
    "pushing",
    "stacking",
    "loading",
    "extracting",
    "bottling",
    "formulating",
    "ordering",
    "tapping",
    "choosing",
    "reconsidering",
    "accumulating",
    "revealing",
    "appearing",
    "dominating",
    "pressuring",
}

UNRELATED_SUBJECT_GUARDRAIL = (
    "Keep the frame physically observable and documentary-like. Show only the explicitly described subject, "
    "environment, and action. Do not replace the idea with symbolic or metaphorical substitutes. "
    "Do not introduce unrelated animals, people, interiors, medical scenes, livestock, zebra-like patterns, "
    "roosters, horseshoe crabs, burial imagery, or surreal allegories."
)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).lower()


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z-]*", normalize_text(text))


def count_term_hits(text: str, terms: set[str]) -> int:
    normalized = normalize_text(text)
    hits = 0
    for term in terms:
        if " " in term:
            if term in normalized:
                hits += 1
        elif re.search(rf"\b{re.escape(term)}\b", normalized):
            hits += 1
    return hits


def is_probably_abstract(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    abstract_hits = count_term_hits(normalized, ABSTRACT_TERMS)
    observable_hits = count_term_hits(normalized, OBSERVABLE_TERMS)
    return abstract_hits > 0 and observable_hits == 0


def lint_prompt_observability(
    prompt: str,
    primary_subject: str = "",
    what_is_in_frame: str = "",
) -> list[str]:
    warnings: list[str] = []
    prompt_text = normalize_text(prompt)
    frame_text = normalize_text(what_is_in_frame)
    subject_text = normalize_text(primary_subject)
    combined = " ".join(part for part in [prompt_text, frame_text, subject_text] if part).strip()

    if not combined:
        return ["Prompt has no observable scene description."]

    if count_term_hits(prompt_text, ABSTRACT_TERMS) >= 2 and count_term_hits(combined, OBSERVABLE_TERMS) < 2:
        warnings.append("Prompt leans abstract and may invite metaphorical substitutions.")

    if not count_term_hits(combined, ENVIRONMENT_TERMS):
        warnings.append("Prompt lacks a clear physical environment.")

    if not count_term_hits(combined, ACTION_TERMS):
        warnings.append("Prompt lacks a concrete observable action or state.")

    if primary_subject and is_probably_abstract(primary_subject):
        warnings.append("Primary subject sounds abstract rather than directly filmable.")

    if not frame_text and count_term_hits(prompt_text, ABSTRACT_TERMS) > 0:
        warnings.append("Abstract prompt is missing a `what_is_in_frame` anchor.")

    return warnings


def build_prompt_guardrail(item: dict[str, Any]) -> str:
    primary_subject = str(item.get("primary_subject", "")).strip()
    what_is_in_frame = str(item.get("what_is_in_frame", "")).strip()
    anchors = []
    if primary_subject:
        anchors.append(f"Primary subject: {primary_subject}.")
    if what_is_in_frame:
        anchors.append(f"Visible frame content: {what_is_in_frame}.")
    anchor_text = " ".join(anchors).strip()
    if anchor_text:
        return f"{anchor_text} {UNRELATED_SUBJECT_GUARDRAIL}"
    return UNRELATED_SUBJECT_GUARDRAIL
