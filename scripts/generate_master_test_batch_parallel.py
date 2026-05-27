import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET


NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

ANCHOR_PLAN = {
    "TOKYO_BOUTIQUE_MAIN": "DC02",
    "TOKYO_NECKLACE_HERO": "DC11",
    "TOKYO_INTRUDER_B": "DC05",
    "TOKYO_INTRUDER_A": "DC06",
    "TOKYO_ASSOCIATE_A": "DC09",
    "TOKYO_GUARD_A": "DC03",
    "FORENSIC_LAB_MAIN": "B0032",
    "BALKAN_SAFEHOUSE_MAIN": "B0034",
    "BALKAN_NETWORK_CORE": "B0031",
}


def run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, check=True, cwd=str(cwd) if cwd else None)


def load_fastgen_module(workspace_root: Path):
    script_path = workspace_root / "scripts" / "fastgen_openai_v4_generate.py"
    spec = importlib.util.spec_from_file_location("fastgen_openai_v4_generate", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load FastGen helper from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["fastgen_openai_v4_generate"] = module
    spec.loader.exec_module(module)
    return module


def fix_mojibake(value: str) -> str:
    if not isinstance(value, str):
        return value
    if any(ch in value for ch in "РСЃЌЋ"):
        try:
            return value.encode("cp1251").decode("utf-8")
        except Exception:
            return value
    return value


def read_xlsx_sheet_objects(xlsx_path: Path, sheet_name: str) -> list[dict]:
    with zipfile.ZipFile(xlsx_path) as zf:
        shared = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("a:si", NS):
                shared.append("".join(t.text or "" for t in si.iterfind(".//a:t", NS)))

        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"].lstrip("/") for rel in rels}

        target = None
        for sheet in wb.find("a:sheets", NS):
            if sheet.attrib["name"] == sheet_name:
                rid = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
                target = rel_map[rid]
                break
        if target is None:
            raise RuntimeError(f"Sheet not found: {sheet_name}")

        root = ET.fromstring(zf.read(target))
        rows = []
        for row in root.find("a:sheetData", NS):
            values = []
            for cell in row.findall("a:c", NS):
                t = cell.attrib.get("t")
                v = cell.find("a:v", NS)
                is_el = cell.find("a:is", NS)
                value = ""
                if t == "s" and v is not None:
                    value = shared[int(v.text)]
                elif t == "inlineStr" and is_el is not None:
                    value = "".join(t2.text or "" for t2 in is_el.iterfind(".//a:t", NS))
                elif v is not None:
                    value = v.text or ""
                values.append(fix_mojibake(value))
            rows.append(values)

    header = rows[0]
    objects = []
    for row in rows[1:]:
        if not any(str(cell).strip() for cell in row):
            continue
        obj = {}
        for idx, key in enumerate(header):
            obj[key] = row[idx] if idx < len(row) else ""
        objects.append(obj)
    return objects


def parse_reference_assets(value: str) -> list[str]:
    assets = []
    for part in value.split(";"):
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
    prompt = row["generation_prompt_final"]
    shot_type = row.get("shot_type", "")
    joined = f"{prompt}\n{shot_type}".lower()
    selected = []
    for asset in assets:
        if asset.endswith("_MAIN"):
            if asset == "FORENSIC_LAB_MAIN" and contains_any(joined, ["forensic", "clinical", "evidence room", "cold white", "stainless"]):
                selected.append(asset)
            elif asset == "BALKAN_SAFEHOUSE_MAIN" and contains_any(joined, ["apartment", "safehouse", "cramped", "tungsten", "prep-room", "meeting space"]):
                selected.append(asset)
            elif asset == "TOKYO_BOUTIQUE_MAIN" and contains_any(joined, ["boutique", "salon", "showroom", "display", "vitrine", "store", "storefront"]):
                selected.append(asset)
        elif asset.endswith("_HERO"):
            if contains_any(joined, ["necklace", "diamond", "stone", "gem", "jewelry", "hero-object", "single-stone"]):
                selected.append(asset)
        elif asset.endswith("_A") or asset.endswith("_B") or asset.endswith("_CORE"):
            if asset == "TOKYO_ASSOCIATE_A" and contains_any(joined, ["employee", "staff", "receptionist", "woman", "handling jewelry"]):
                selected.append(asset)
            elif asset == "TOKYO_GUARD_A" and contains_any(joined, ["guard", "security guard", "earpiece"]):
                selected.append(asset)
            elif asset == "TOKYO_INTRUDER_A" and contains_any(joined, ["one man", "single man", "his gaze", "affluent-looking man", "returning visitor", "he scans"]):
                selected.append(asset)
            elif asset == "TOKYO_INTRUDER_B" and contains_any(joined, ["two men", "pair", "they enter", "two well-dressed men", "clients"]):
                selected.append(asset)
            elif asset == "BALKAN_NETWORK_CORE" and contains_any(joined, ["network", "men", "faces", "planning", "drivers", "civilian clothes", "weathered knuckles"]):
                selected.append(asset)
    return selected


def write_report(path: Path, title: str, lines: list[str]) -> None:
    path.write_text("\n".join([f"# {title}", "", *lines]) + "\n", encoding="utf-8")


def classify_failure_action(error_text: str) -> str:
    lowered = (error_text or "").lower()
    policy_markers = [
        "content policies",
        "policy",
        "запрос на генерацию изображения был отклонён политикой",
        "violat",
        "rejected by openai content policy",
    ]
    if any(marker in lowered for marker in policy_markers):
        return "rewrite_prompt"
    return "retry_generation"


def stable_hash(payload: object) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--xlsx-path", required=True)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--start-row", type=int, default=1)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--shared-images-dir", default="")
    parser.add_argument("--seed-reference-registry", default="")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    workspace_root = project_root.parents[1]
    xlsx_path = Path(args.xlsx_path).resolve()
    run_root = project_root / "video_runs" / args.run_name
    if run_root.exists():
        shutil.rmtree(run_root)

    planning_dir = run_root / "planning"
    prompts_dir = run_root / "prompts"
    fastgen_dir = run_root / "fastgen_run"
    anchors_dir = run_root / "anchors"
    generated_dir = run_root / "assets" / "images" / "generated"
    logs_dir = run_root / "logs"
    for directory in [planning_dir, prompts_dir, fastgen_dir, anchors_dir, generated_dir, logs_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    fastgen = load_fastgen_module(workspace_root)
    api_key = fastgen.load_env_key()
    all_rows = read_xlsx_sheet_objects(xlsx_path, "Generation_Master")
    start_index = max(0, args.start_row - 1)
    end_index = start_index + args.limit if args.limit > 0 else len(all_rows)
    rows = all_rows[start_index:end_index]
    rows_by_id = {row["id"]: row for row in rows}
    planning_dir.joinpath("selected_rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    write_report(
        logs_dir / "input_check_report.md",
        "Input Check Report",
        [
            f"- Workbook present: {'OK' if xlsx_path.exists() else 'MISSING'}",
            f"- FAST_GEN_API_KEY available: {'OK' if api_key else 'MISSING'}",
            f"- Rows selected: {len(rows)}",
            f"- Concurrency target: {args.concurrency}",
            "- Strategy: generate canonical anchors first, then run the remaining batch in parallel with targeted refs",
        ],
    )

    registry: dict[str, str] = {}
    if args.seed_reference_registry:
        seed_registry_path = Path(args.seed_reference_registry).resolve()
        if seed_registry_path.exists():
            registry.update(json.loads(seed_registry_path.read_text(encoding="utf-8")))
    anchor_manifest = []
    anchor_failures = []
    for asset_id, row_id in ANCHOR_PLAN.items():
        if asset_id in registry:
            anchor_manifest.append({"asset_id": asset_id, "row_id": row_id, "operation_id": "seeded", "path": registry[asset_id]})
            continue
        row = rows_by_id.get(row_id)
        if row is None:
            continue
        try:
            operation = fastgen.create_operation(api_key, row["generation_prompt_final"], [], "1920x1080", "16:9")
            status = fastgen.poll_operation(api_key, operation["operation_id"], poll_seconds=3.0, max_polls=120)
            target_path = anchors_dir / f"{asset_id}.png"
            fastgen.write_data_uri_image(status["result"][0], target_path)
            registry[asset_id] = str(target_path)
            anchor_manifest.append({"asset_id": asset_id, "row_id": row_id, "operation_id": operation["operation_id"], "path": str(target_path)})
            print(f"anchor {asset_id} <- {row_id}")
        except Exception as exc:
            anchor_failures.append({"asset_id": asset_id, "row_id": row_id, "error": str(exc)})
            print(f"anchor failed {asset_id} <- {row_id}: {exc}")

    (fastgen_dir / "reference_registry.json").write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    (fastgen_dir / "anchor_manifest.json").write_text(json.dumps(anchor_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (fastgen_dir / "anchor_failed.json").write_text(json.dumps(anchor_failures, ensure_ascii=False, indent=2), encoding="utf-8")

    refs_json_path = prompts_dir / "fastgen_ref_paths.json"
    refs_json_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")

    prompt_blocks = []
    batch_rows = []
    package_items = []
    for row in rows:
        scene_number = start_index + len(batch_rows) + 1
        assets = parse_reference_assets(row.get("reference_assets_needed", ""))
        relevant = [asset for asset in classify_relevant_assets(row, assets) if asset in registry]
        if relevant:
            prefix = "Use reference image: " if len(relevant) == 1 else "Use reference images: "
            refs_text = relevant[0] if len(relevant) == 1 else ", ".join(relevant)
            prompt_blocks.append(f"{prefix}{refs_text}. {row['generation_prompt_final']}")
        else:
            prompt_blocks.append(f"No character reference. {row['generation_prompt_final']}")
        batch_rows.append(
            {
                "id": row["id"],
                "scene_id": f"scene_{scene_number:04d}",
                "relevant_assets": relevant,
                "preferred_prompt_tier": row["preferred_prompt_tier"],
            }
        )
        package_items.append(
            {
                "scene_id": f"scene_{scene_number:04d}",
                "beat_priority": "standard",
                "key_beat": False,
                "variant_count": 1,
            }
        )

    prompts_md_path = prompts_dir / "fastgen_prompts_generator_ready.md"
    export_text = "\n\n".join(prompt_blocks) + "\n"
    prompts_md_path.write_text(export_text, encoding="utf-8")
    export_meta = {
        "package_path": str(planning_dir / "selected_rows.json"),
        "package_signature": stable_hash(batch_rows),
        "prompt_count": len(batch_rows),
        "package_items": package_items,
    }
    export_meta["export_signature"] = stable_hash(
        {
            "package_path": export_meta["package_path"],
            "package_signature": export_meta["package_signature"],
            "prompt_count": export_meta["prompt_count"],
            "content": export_text,
        }
    )
    prompts_md_path.with_suffix(prompts_md_path.suffix + ".meta.json").write_text(
        json.dumps(export_meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    planning_dir.joinpath("batch_rows.json").write_text(json.dumps(batch_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    command = [
        "python",
        str(workspace_root / "scripts" / "fastgen_openai_v4_generate.py"),
        "--prompts",
        str(prompts_md_path),
        "--refs",
        str(refs_json_path),
        "--workdir",
        str(fastgen_dir),
        "--concurrency",
        str(args.concurrency),
    ]
    if args.shared_images_dir:
        command.extend(["--images-dir", str(Path(args.shared_images_dir).resolve())])
    run(command, cwd=workspace_root)

    image_dir = Path(args.shared_images_dir).resolve() if args.shared_images_dir else fastgen_dir / "images"
    for file in image_dir.glob("*.png"):
        shutil.copy2(file, generated_dir / file.name)

    failed_jsonl = fastgen_dir / "failed.jsonl"
    deferred_retry = []
    retry_generation = []
    rewrite_prompt = []
    if failed_jsonl.exists():
        failed_items = [json.loads(line) for line in failed_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
        for failed in failed_items:
            source_index = int(failed["index"]) - 1
            if 0 <= source_index < len(rows):
                row = rows[source_index]
                item = {
                    "id": row["id"],
                    "section": row["section"],
                    "preferred_prompt_tier": row["preferred_prompt_tier"],
                    "reference_assets_needed": row["reference_assets_needed"],
                    "generation_prompt_final": row["generation_prompt_final"],
                    "error": failed.get("error"),
                    "postrun_action": classify_failure_action(failed.get("error", "")),
                }
                deferred_retry.append(item)
                if item["postrun_action"] == "rewrite_prompt":
                    rewrite_prompt.append(item)
                else:
                    retry_generation.append(item)
    (fastgen_dir / "deferred_retry_manifest.json").write_text(json.dumps(deferred_retry, ensure_ascii=False, indent=2), encoding="utf-8")
    (fastgen_dir / "retry_generation_manifest.json").write_text(json.dumps(retry_generation, ensure_ascii=False, indent=2), encoding="utf-8")
    (fastgen_dir / "rewrite_prompt_manifest.json").write_text(json.dumps(rewrite_prompt, ensure_ascii=False, indent=2), encoding="utf-8")

    write_report(
        logs_dir / "generation_report.md",
        "Generation Report",
        [
            f"- Anchor refs generated: {len(anchor_manifest)}",
            f"- Anchor refs failed: {len(anchor_failures)}",
            f"- Batch prompts: {len(batch_rows)}",
            f"- Prompt file: {prompts_md_path}",
            f"- Refs map: {refs_json_path}",
            f"- Output images: {generated_dir}",
            f"- Deferred retry manifest: {fastgen_dir / 'deferred_retry_manifest.json'}",
            f"- Retry-generation manifest: {fastgen_dir / 'retry_generation_manifest.json'}",
            f"- Rewrite-prompt manifest: {fastgen_dir / 'rewrite_prompt_manifest.json'}",
            "- Failed prompts are not re-sent during the same run; they are queued for a separate post-run action after the full batch completes.",
            "- Policy/content-policy failures are classified as rewrite_prompt; network, timeout, storage, and internal failures are classified as retry_generation.",
        ],
    )


if __name__ == "__main__":
    main()
