import hashlib
import json
from datetime import datetime
from pathlib import Path


ROOT = Path(r"C:\Users\MIKE\Documents\Codex\YT")
BASE = ROOT / "projects" / "rozovye_pantery_001" / "video_runs" / "master_first50_seeded_parallel_20260526"
FASTGEN_RUN = BASE / "fastgen_run"


REWRITES = {
    "scene_0025": (
        "Create a premium cinematic documentary still in 16:9. "
        "Scene meaning: the legend dissolves into ordinary evidence once the adrenaline is gone. "
        "Visual intent: replace criminal glamour with tired, procedural aftermath. "
        "Main subject: an empty utilitarian room that suggests a temporary network once passed through it, without showing active planning or action. "
        "Action without speech: no people perform anything; the room simply holds traces of coordination already over. "
        "Environment storytelling: plain chairs, a worn table, a folded city map turned face down, ordinary jackets on hooks, a keyring beside disposable cups, muted window light. "
        "Composition: layered medium-wide documentary tableau with no heroic focal point. "
        "Camera: realistic documentary still. "
        "Lighting: grey daylight and tired tungsten. "
        "Mood: drained, procedural, anti-romantic. "
        "Important details: scuffed tabletop, plain car keys, folded paper edge, mismatched chairs, paper cups. "
        "Restrictions: no active crime, no weapons, no tactical preparation, no readable text, no glamorized figures. "
        "Continuity requirements: use TOKYO_BOUTIQUE_MAIN whenever the interior returns. Only attach character references when the same person is visible again; otherwise use no character reference. Preserve the same lighting family, floor material, display geometry, and necklace silhouette across adjacent beats. "
        "Consistency anchor: Keep the Tokyo boutique stable: polished stone floor, warm gold showcase pools, cold surveillance spill, thick glass seams, layered reflections, high-end Japanese service etiquette. "
        "Recurring motif priority: glass reflections; surveillance domes; velvet and absence; warm luxury versus cold control If no recurring person is visible, use no character reference and preserve only the location/material continuity."
    ),
    "scene_0038": (
        "Create a premium cinematic documentary still in 16:9. "
        "Scene meaning: the nickname hides a colder administrative reality visible only in the evidence left behind. "
        "Visual intent: explain the network as an investigative puzzle, not as a live operational scene. "
        "Main subject: a forensic tabletop where anonymous fragments suggest coordination across places without depicting instruction or planning. "
        "Action without speech: gloved hands have just arranged evidence, but the frame catches the stillness after that action. "
        "Environment storytelling: cold evidence room, sealed bags, map fragments turned partly away, object tags out of focus, stainless surface. "
        "Composition: top-down evidence-table shot, layered foreground and background storytelling, realistic documentary optics. "
        "Lighting: cold forensic light. "
        "Mood: procedural chill, analytical tension. "
        "Important details: sealed cosmetic jar, worn duffel fabric, map corner, gloved fingertips, stainless reflections. "
        "Style: photorealistic premium documentary realism, natural textures, believable surfaces, no cheap AI polish. "
        "Restrictions: no active plotting, no readable text, no fake UI, no deformed anatomy, no glamorized criminal staging. "
        "Reference policy: use FORENSIC_LAB_MAIN for clinical evidence beats and BALKAN_SAFEHOUSE_MAIN for worn civilian interiors. Do not force character references into object-led shots. "
        "Consistency anchor: Hold the forensic world cold white and stainless; keep any civilian remnants worn, ordinary, and unsensational. "
        "Recurring motif priority: cream jar residue; weathered materials; cheap table; cold evidence light If no recurring person is visible, use no character reference and preserve only the location/material continuity."
    ),
    "scene_0039": (
        "Create a premium cinematic documentary still in 16:9. "
        "Scene meaning: a strange everyday object can become the thread that lets investigators reconstruct a much larger story. "
        "Visual intent: turn the cosmetic jar into a procedural clue rather than a clever trick. "
        "Main subject: a sealed cosmetic jar on a forensic tray under clinical light, treated as evidence rather than revelation. "
        "Action without speech: a gloved hand steadies the tray while the jar remains the quiet center of attention. "
        "Environment storytelling: stainless lab surface, blurred evidence bags, numbered markers turned unreadable, restrained depth. "
        "Composition: macro evidence close-up with layered background blur, realistic documentary optics. "
        "Lighting: stark clinical light with soft falloff. "
        "Mood: curiosity, restraint, procedural focus. "
        "Important details: residue at the lid seam, tray scratches, nitrile glove texture, diffused bag shapes. "
        "Style: photorealistic premium documentary realism, natural textures, believable surfaces, no cheap AI polish. "
        "Restrictions: no hidden-object reveal gimmick, no readable text, no fake UI, no deformed anatomy, no sensational crime mood. "
        "Reference policy: use FORENSIC_LAB_MAIN for clinical evidence beats and BALKAN_SAFEHOUSE_MAIN only when a worn civilian room is directly shown. Do not force character references into object-only shots. "
        "Consistency anchor: Hold the forensic lab cold white and stainless, with ordinary evidence handling and restrained composition. "
        "Recurring motif priority: cream jar residue; weathered hands; cheap table; cold evidence light If no recurring person is visible, use no character reference and preserve only the location/material continuity."
    ),
    "scene_0041": (
        "Create a premium cinematic documentary still in 16:9. "
        "Scene meaning: what looks legendary from a distance becomes banal and troubling when reduced to ordinary traces and human labor. "
        "Visual intent: close the escalation on consequence and investigation rather than on operational mystique. "
        "Main subject: close-up forensic handling of mundane items linked to the case, with human presence reduced to careful evidence work. "
        "Action without speech: gloved hands sort and separate ordinary objects on a table after the fact. "
        "Environment storytelling: cold evidence room, shallow bins, stainless edge, neutral background blur, no dramatic set dressing. "
        "Composition: close-up hands with layered tabletop detail, realistic documentary optics. "
        "Lighting: weak overhead white light with soft shadow. "
        "Mood: grim, procedural, unsensational. "
        "Important details: gloved fingertips, scuffed object surfaces, tray edge, muted reflections, ordinary materials. "
        "Style: photorealistic premium documentary realism, natural textures, believable surfaces, no cheap AI polish. "
        "Restrictions: no active crime, no instructional layout, no readable text, no fake UI, no deformed anatomy, no glamorized figures. "
        "Reference policy: use FORENSIC_LAB_MAIN for clinical evidence beats and BALKAN_SAFEHOUSE_MAIN only when that environment is directly visible. Do not force character references into object-led shots. "
        "Consistency anchor: Hold the forensic lab cold white and stainless, with all props feeling ordinary, handled, and unheroic. "
        "Recurring motif priority: cream jar residue; weathered materials; cheap table; cold evidence light If no recurring person is visible, use no character reference and preserve only the location/material continuity."
    ),
}


def stable_hash(payload: object) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def build_block(refs: list[str], prompt: str) -> str:
    if not refs:
        return f"No character reference. {prompt.strip()}"
    if len(refs) == 1:
        return f"Use reference image: {refs[0]}. {prompt.strip()}"
    return f"Use reference images: {', '.join(refs)}. {prompt.strip()}"


def main() -> None:
    rewrite_manifest = json.loads((FASTGEN_RUN / "rewrite_prompt_manifest.json").read_text(encoding="utf-8"))
    ref_map = json.loads((BASE / "prompts" / "fastgen_ref_paths.json").read_text(encoding="utf-8"))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    retry_dir = BASE / "retries" / f"retry_policy_{timestamp}"
    prompts_dir = retry_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    rewritten_items = []
    package_items = []
    blocks = []

    for item in rewrite_manifest:
        scene_id = item["scene_id"]
        prompt = REWRITES.get(scene_id)
        if not prompt:
            raise KeyError(f"Missing rewrite for {scene_id}")
        rewritten = dict(item)
        rewritten["original_prompt"] = item["prompt"]
        rewritten["prompt"] = prompt
        rewritten_items.append(rewritten)
        package_items.append(
            {
                "scene_id": rewritten["scene_id"],
                "beat_priority": rewritten.get("beat_priority", "standard"),
                "key_beat": bool(rewritten.get("key_beat", False)),
                "variant_count": int(rewritten.get("variant_count", 1) or 1),
            }
        )
        blocks.append(build_block(rewritten.get("refs", []), rewritten["prompt"]))

    prompts_path = prompts_dir / "policy_rewrite_prompts_generator_ready.md"
    export_text = "\n\n".join(blocks).strip() + "\n"
    prompts_path.write_text(export_text, encoding="utf-8")

    meta = {
        "package_path": str(FASTGEN_RUN / "rewrite_prompt_manifest.json"),
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

    (prompts_dir / "fastgen_ref_paths.json").write_text(json.dumps(ref_map, ensure_ascii=False, indent=2), encoding="utf-8")
    (retry_dir / "rewritten_policy_manifest.json").write_text(
        json.dumps(rewritten_items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"retry_dir": str(retry_dir), "count": len(rewritten_items)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
