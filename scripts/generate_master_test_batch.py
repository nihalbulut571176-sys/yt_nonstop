import argparse
import importlib.util
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET


NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


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
            if contains_any(joined, ["necklace", "diamond", "stone", "gem", "jewelry", "jar revealing a hidden diamond"]):
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


def assign_anchor_assets(row: dict, assets: list[str]) -> list[str]:
    prompt = row["generation_prompt_final"]
    shot_type = row.get("shot_type", "")
    joined = f"{prompt}\n{shot_type}".lower()
    anchors = []
    for asset in assets:
        if asset == "TOKYO_BOUTIQUE_MAIN" and contains_any(joined, ["boutique", "salon", "showroom", "wide architectural", "surveillance viewpoint", "sales-floor", "doorway"]):
            anchors.append(asset)
        elif asset == "TOKYO_NECKLACE_HERO" and contains_any(joined, ["necklace", "diamond", "stone", "gem", "hero-object", "single-stone", "massive diamond"]):
            anchors.append(asset)
        elif asset == "TOKYO_INTRUDER_A" and contains_any(joined, ["one man", "single man", "his gaze", "affluent-looking man"]):
            anchors.append(asset)
        elif asset == "TOKYO_INTRUDER_B" and contains_any(joined, ["two men", "pair", "they enter", "two well-dressed men"]):
            anchors.append(asset)
        elif asset == "TOKYO_ASSOCIATE_A" and contains_any(joined, ["employee", "staff", "receptionist", "woman"]):
            anchors.append(asset)
        elif asset == "TOKYO_GUARD_A" and contains_any(joined, ["guard", "security guard", "earpiece"]):
            anchors.append(asset)
        elif asset == "FORENSIC_LAB_MAIN" and contains_any(joined, ["forensic", "clinical", "evidence room", "cold white", "stainless"]):
            anchors.append(asset)
        elif asset == "BALKAN_SAFEHOUSE_MAIN" and contains_any(joined, ["apartment", "safehouse", "cramped", "tungsten", "prep-room", "meeting space"]):
            anchors.append(asset)
        elif asset == "BALKAN_NETWORK_CORE" and contains_any(joined, ["network", "men", "faces", "planning", "civilian clothes"]):
            anchors.append(asset)
    return anchors


def write_report(path: Path, title: str, lines: list[str]) -> None:
    path.write_text("\n".join([f"# {title}", "", *lines]) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--xlsx-path", required=True)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--run-name", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    workspace_root = project_root.parents[1]
    xlsx_path = Path(args.xlsx_path).resolve()
    run_root = project_root / "video_runs" / args.run_name
    if run_root.exists():
        shutil.rmtree(run_root)

    prompts_dir = run_root / "prompts"
    fastgen_dir = run_root / "fastgen_run"
    generated_dir = run_root / "assets" / "images" / "generated"
    logs_dir = run_root / "logs"
    planning_dir = run_root / "planning"
    meta_dir = fastgen_dir / "meta"
    image_dir = fastgen_dir / "images"
    for directory in [prompts_dir, fastgen_dir, generated_dir, logs_dir, planning_dir, meta_dir, image_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    fastgen = load_fastgen_module(workspace_root)
    rows = read_xlsx_sheet_objects(xlsx_path, "Generation_Master")[: args.limit]
    if not rows:
        raise RuntimeError("No rows selected from workbook")

    planning_path = planning_dir / "selected_rows.json"
    planning_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(
        logs_dir / "input_check_report.md",
        "Input Check Report",
        [
            f"- Workbook present: {'OK' if xlsx_path.exists() else 'MISSING'}",
            f"- FAST_GEN_API_KEY available: {'OK' if fastgen.load_env_key() else 'MISSING'}",
            f"- Rows selected: {len(rows)}",
            f"- Run root: {run_root}",
        ],
    )

    prompts_path = prompts_dir / "generator_prompts.json"
    prompts_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    api_key = fastgen.load_env_key()
    registry: dict[str, dict] = {}
    success_log_path = fastgen_dir / "success.jsonl"
    failed_log_path = fastgen_dir / "failed.jsonl"
    manifest = []

    for index, row in enumerate(rows, start=1):
        assets = parse_reference_assets(row.get("reference_assets_needed", ""))
        relevant_assets = classify_relevant_assets(row, assets)
        attached_assets = [asset for asset in relevant_assets if asset in registry]
        attached_assets = attached_assets[:4]
        ref_paths = [Path(registry[asset]["path"]) for asset in attached_assets]
        ref_hashes = [fastgen.upload_reference(api_key, ref_path) for ref_path in ref_paths]

        output_name = f"{row['id']}_V01.png"
        operation = fastgen.create_operation(
            api_key=api_key,
            prompt=row["generation_prompt_final"],
            refs=ref_hashes,
            size="1920x1080",
            aspect_ratio="16:9",
        )
        status = fastgen.poll_operation(api_key, operation["operation_id"], poll_seconds=3.0, max_polls=120)
        target_path = image_dir / output_name
        fastgen.write_data_uri_image(status["result"][0], target_path)
        shutil.copy2(target_path, generated_dir / output_name)

        anchors = assign_anchor_assets(row, assets)
        for asset in anchors:
            registry[asset] = {"path": str(target_path), "source_id": row["id"]}

        meta = {
            "index": index,
            "id": row["id"],
            "section": row["section"],
            "recurring_world": row["recurring_world"],
            "preferred_prompt_tier": row["preferred_prompt_tier"],
            "operation_id": operation["operation_id"],
            "output": str(target_path),
            "attached_assets": attached_assets,
            "promised_assets": assets,
            "anchored_assets": anchors,
        }
        manifest.append(meta)
        (meta_dir / f"{index:03d}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        with success_log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(meta, ensure_ascii=False) + "\n")
        print(f"done {index:03d} {row['id']} refs={attached_assets}")

    (fastgen_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (fastgen_dir / "reference_registry.json").write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    (fastgen_dir / "run_summary.json").write_text(
        json.dumps({"done": len(manifest), "failed": 0, "limit": args.limit}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_report(
        logs_dir / "generation_report.md",
        "Generation Report",
        [
            f"- Workbook: {xlsx_path}",
            f"- Rows generated: {len(manifest)}",
            f"- Output dir: {generated_dir}",
            f"- Manifest: {fastgen_dir / 'run_manifest.json'}",
            f"- Registry: {fastgen_dir / 'reference_registry.json'}",
            "- Generation strategy: clean-from-scratch reference chaining inside this run",
        ],
    )


if __name__ == "__main__":
    main()
