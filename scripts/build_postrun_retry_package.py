import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path


def stable_hash(payload: object) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def parse_reference_assets(value: str) -> list[str]:
    assets = []
    for part in (value or "").split(";"):
        token = part.strip()
        if not token:
            continue
        token = re.split(r"\s+(?:when|for|only)\b", token, maxsplit=1)[0].strip()
        if token:
            assets.append(token)
    return assets


def contains_any(text: str, needles: list[str]) -> bool:
    lowered = text.lower()
    return any(needle in lowered for needle in needles)


def classify_relevant_assets(row: dict, assets: list[str]) -> list[str]:
    prompt = row.get("generation_prompt_final", "")
    shot_type = row.get("shot_type", "")
    joined = f"{prompt}\n{shot_type}".lower()
    selected = []
    for asset in assets:
        if asset.endswith("_MAIN"):
            if asset == "FORENSIC_LAB_MAIN" and contains_any(joined, ["forensic", "clinical", "evidence room", "cold white", "stainless"]):
                selected.append(asset)
            elif asset == "BALKAN_SAFEHOUSE_MAIN" and contains_any(joined, ["apartment", "safehouse", "cramped", "tungsten", "meeting space"]):
                selected.append(asset)
            elif asset == "TOKYO_BOUTIQUE_MAIN" and contains_any(joined, ["boutique", "salon", "showroom", "display", "vitrine", "store", "storefront"]):
                selected.append(asset)
            elif asset == "LUXURY_BOUTIQUE_SYSTEM_MAIN" and contains_any(joined, ["boutique", "guard", "control desk", "display", "security", "store"]):
                selected.append(asset)
            elif asset == "BIARRITZ_BENCH_MAIN" and contains_any(joined, ["bench", "street", "paint", "crowd", "camera dome"]):
                selected.append(asset)
            elif asset == "WAFI_MALL_MAIN" and contains_any(joined, ["mall", "marble", "glass facade", "night exterior"]):
                selected.append(asset)
            elif asset == "GLOBAL_ANALYSIS_ROOM" and contains_any(joined, ["analyst", "coordination room", "paperwork", "office", "case fragments"]):
                selected.append(asset)
            elif asset == "PREMIUM_STOREFRONT_RECON" and contains_any(joined, ["storefront", "display reflections", "premium retail", "street"]):
                selected.append(asset)
        elif asset.endswith("_HERO"):
            if contains_any(joined, ["necklace", "diamond", "stone", "gem", "jewelry"]):
                selected.append(asset)
        elif asset.endswith("_A") or asset.endswith("_B") or asset.endswith("_CORE") or asset.endswith("_SET") or asset.endswith("_WORLD") or asset.endswith("_CARS"):
            selected.append(asset)
    return selected


def build_block(refs: list[str], prompt: str) -> str:
    if not refs:
        return f"No character reference. {prompt.strip()}"
    if len(refs) == 1:
        return f"Use reference image: {refs[0]}. {prompt.strip()}"
    return f"Use reference images: {', '.join(refs)}. {prompt.strip()}"


def extract_concrete_details(prompt: str) -> list[str]:
    details = []
    candidates = [
        "wet paint sheen",
        "camera dome in frame edge",
        "parked car blocking sightline",
        "person dissolving into crowd flow",
        "customer cluster creating cover",
        "guard half-turn",
        "button not yet pressed",
        "door seam",
        "broken glass edges",
        "untouched tray beside target tray",
        "glass cloud",
        "skid marks",
        "frozen shoppers",
        "lingering glance",
        "staff posture",
        "camera on lamppost",
        "curbside choke point",
        "blurred mugshot fragments",
        "stacks of translated paperwork",
        "fatigued analyst silhouettes",
        "city photos without readable labels",
    ]
    lowered = prompt.lower()
    for item in candidates:
        if item.lower() in lowered:
            details.append(item)
    return details[:4]


def rewrite_prompt(row: dict) -> str:
    section = (row.get("section") or "").lower()
    original = row.get("generation_prompt_final", "")
    details = extract_concrete_details(original)

    if "security as delay" in section:
        detail_line = details or ["door seam", "control desk", "camera coverage", "display reflections"]
        return (
            "Create a premium cinematic documentary still in 16:9. "
            "Scene meaning: the film explains how a luxury security system creates delay between observation, decision, and response. "
            "Visual intent: investigative documentary frame about systemic vulnerability, not live criminal action. "
            "Main subject: a high-end jewelry boutique read as a timing puzzle of doors, cameras, counters, and sightlines. "
            "Action without speech: staff and visitors remain ordinary and quiet while the architecture reveals the lag inside the system. "
            "Environment storytelling: elegant boutique materials, surveillance hardware, soft retail warmth, and colder monitor spill around the control area. "
            "Composition: layered documentary still with foreground obstruction and readable spatial depth. "
            "Camera: realistic documentary photography, natural lens perspective, cinematic framing. "
            "Lighting: balanced luxury interior light with cooler security accents. "
            "Mood: analytical tension, quiet unease. "
            f"Important details: {', '.join(detail_line)}. "
            "Style: premium cinematic documentary still, photorealistic, believable textures, subtle imperfections. "
            "Restrictions: no live attack, no break-in, no tactical action, no readable text, no fake UI, no glamorized criminal framing."
        )

    if "crime geometry in public space" in section:
        detail_line = details or ["wet paint sheen", "camera dome in frame edge", "parked car blocking sightline", "crowd flow masking visibility"]
        return (
            "Create a premium cinematic documentary still in 16:9. "
            "Scene meaning: ordinary urban objects and crowd behavior can quietly distort visibility and weaken witness clarity. "
            "Visual intent: public-space investigation frame about ambiguity, surveillance limits, and city geometry. "
            "Main subject: a luxury retail street where benches, parked cars, pedestrians, and reflections interfere with a clean line of sight. "
            "Action without speech: pedestrians move normally and the frame captures the quiet confusion of a camera seeing too much and understanding too little. "
            "Environment storytelling: European premium storefronts, polished glass, street furniture, curb edges, and subtle surveillance presence. "
            "Composition: documentary street still with layered foreground obstruction and deep background flow. "
            "Camera: realistic documentary photography, natural lens perspective, cinematic framing. "
            "Lighting: natural city light with believable reflections on glass and pavement. "
            "Mood: quiet calculation, institutional unease. "
            f"Important details: {', '.join(detail_line)}. "
            "Style: premium cinematic documentary still, photorealistic, believable textures, subtle imperfections. "
            "Restrictions: no getaway staging, no operational choreography, no glamorized suspects, no readable text, no fake UI."
        )

    if "discipline over greed" in section:
        detail_line = details or ["broken glass edges", "untouched tray", "empty display gap", "luxury debris under harsh light"]
        return (
            "Create a premium cinematic documentary still in 16:9. "
            "Scene meaning: the aftermath shows selective loss and controlled damage more clearly than any legend does. "
            "Visual intent: evidence-led documentary frame focused on consequence, restraint, and what remains untouched. "
            "Main subject: a damaged luxury interior after the event, with absence and selection visible in the displays rather than action in progress. "
            "Action without speech: no live confrontation; the scene is already still, leaving only material evidence and institutional aftermath. "
            "Environment storytelling: cracked glass, expensive surfaces, emptied focal display areas, and ignored luxury items still in place. "
            "Composition: medium documentary still with layered debris and a readable focal gap. "
            "Camera: realistic documentary photography, natural lens perspective, cinematic framing. "
            "Lighting: harsh incident light mixed with residual boutique warmth. "
            "Mood: drained, procedural, unsensational. "
            f"Important details: {', '.join(detail_line)}. "
            "Style: premium cinematic documentary still, photorealistic, believable textures, subtle imperfections. "
            "Restrictions: no active raid, no weapons, no tactical poses, no readable text, no glamorized criminal framing."
        )

    return (
        "Create a premium cinematic documentary still in 16:9. "
        "Scene meaning: the documentary focuses on evidence, consequence, and institutional understanding rather than live criminal action. "
        "Visual intent: investigative frame with realistic environments, restrained tension, and no glamorization. "
        "Main subject: a believable documentary environment tied to security, investigation, or aftermath. "
        "Action without speech: the frame captures stillness after the important moment, leaving systems and traces to tell the story. "
        "Environment storytelling: realistic materials, layered space, subtle surveillance or evidence cues, and no readable text. "
        "Composition: layered documentary still, natural perspective, cinematic framing. "
        "Lighting: motivated practical light with restrained contrast. "
        "Mood: analytical unease. "
        "Important details: case fragments, material traces, institutional fatigue, spatial tension. "
        "Style: premium cinematic documentary still, photorealistic, believable textures, subtle imperfections. "
        "Restrictions: no live crime, no tactical staging, no readable text, no fake UI, no glamorized figures."
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-run", required=True)
    parser.add_argument("--mode", required=True, choices=["retry_generation", "rewrite_prompt"])
    args = parser.parse_args()

    base_run = Path(args.base_run).resolve()
    fastgen_run = base_run / "fastgen_run"
    planning_dir = base_run / "planning"
    prompts_dir = base_run / "prompts"
    retries_dir = base_run / "retries"
    retries_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = fastgen_run / f"{args.mode}_manifest.json"
    items = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = json.loads((planning_dir / "selected_rows.json").read_text(encoding="utf-8"))
    ref_map = json.loads((prompts_dir / "fastgen_ref_paths.json").read_text(encoding="utf-8"))
    rows_by_id = {row["id"]: row for row in rows}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    retry_prefix = "retry_technical" if args.mode == "retry_generation" else "retry_policy"
    retry_dir = retries_dir / f"{retry_prefix}_{timestamp}"
    retry_prompts_dir = retry_dir / "prompts"
    retry_prompts_dir.mkdir(parents=True, exist_ok=True)

    rewritten_items = []
    package_items = []
    blocks = []

    for item in items:
        row = rows_by_id[item["id"]]
        scene_number = int(str(item["id"]).lstrip("B"))
        scene_id = f"scene_{scene_number:04d}"
        assets = parse_reference_assets(row.get("reference_assets_needed", ""))
        relevant_assets = [asset for asset in classify_relevant_assets(row, assets) if asset in ref_map]
        prompt = row["generation_prompt_final"] if args.mode == "retry_generation" else rewrite_prompt(row)

        rewritten_items.append(
            {
                "id": row["id"],
                "scene_id": scene_id,
                "section": row.get("section", ""),
                "original_prompt": row.get("generation_prompt_final", ""),
                "prompt": prompt,
                "refs": relevant_assets,
                "error": item.get("error", ""),
                "postrun_action": args.mode,
            }
        )
        package_items.append(
            {
                "scene_id": scene_id,
                "beat_priority": "standard",
                "key_beat": False,
                "variant_count": 1,
            }
        )
        blocks.append(build_block(relevant_assets, prompt))

    prompts_path = retry_prompts_dir / f"{args.mode}_prompts_generator_ready.md"
    export_text = "\n\n".join(blocks).strip() + "\n"
    prompts_path.write_text(export_text, encoding="utf-8")

    meta = {
        "package_path": str(manifest_path),
        "package_signature": stable_hash(rewritten_items),
        "prompt_count": len(rewritten_items),
        "package_items": package_items,
    }
    meta["export_signature"] = stable_hash(
        {
            "package_path": meta["package_path"],
            "package_signature": meta["package_signature"],
            "prompt_count": meta["prompt_count"],
            "content": export_text,
        }
    )
    prompts_path.with_suffix(prompts_path.suffix + ".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    (retry_prompts_dir / "fastgen_ref_paths.json").write_text(
        json.dumps(ref_map, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    manifest_copy_name = "rewritten_policy_manifest.json" if args.mode == "rewrite_prompt" else "retry_generation_package.json"
    (retry_dir / manifest_copy_name).write_text(json.dumps(rewritten_items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"retry_dir": str(retry_dir), "count": len(rewritten_items), "mode": args.mode}, ensure_ascii=False))


if __name__ == "__main__":
    main()
