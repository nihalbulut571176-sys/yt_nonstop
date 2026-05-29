from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from yt_nonstop.contracts.validators import STAGE_CHOICES, validate_stage
from yt_nonstop.pipeline.orchestrator import run_pipeline
from yt_nonstop.pipeline.artifact_paths import STAGE_SEQUENCE
from yt_nonstop.pipeline.project_config import load_project
from yt_nonstop.pipeline.project_status import build_project_status, format_project_status


ROOT = Path(__file__).resolve().parents[2]


def _status_command(args: argparse.Namespace) -> int:
    dashboard = build_project_status(Path(args.project_json), stage=args.stage, state_db_override=args.state_db or None)
    if args.json:
        print(json.dumps(dashboard.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_project_status(dashboard, include_failed=args.failed))
    return 0


def _validate_command(args: argparse.Namespace) -> int:
    project = load_project(Path(args.project_json).resolve())
    stages = list(STAGE_CHOICES[:-1]) if args.stage == "all" else [args.stage]
    report = {"project_id": project["project_id"], "stage": args.stage, "status": "passed", "errors": [], "warnings": [], "stage_results": []}
    for stage in stages:
        errors, warnings = validate_stage(project, stage)
        report["stage_results"].append({"stage": stage, "status": "failed" if errors else "passed", "errors": errors, "warnings": warnings})
        report["errors"].extend(f"[{stage}] {item}" for item in errors)
        report["warnings"].extend(f"[{stage}] {item}" for item in warnings)
    if report["errors"]:
        report["status"] = "failed"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


def _render_command(args: argparse.Namespace) -> int:
    project = load_project(Path(args.project_json).resolve())
    from_stage = args.from_stage or ("timeline" if project.get("render", {}).get("status") not in {"timeline_built", "completed"} else "render")
    run_args = build_parser().parse_args(
        [
            "run",
            "--project-json",
            args.project_json,
            "--from",
            from_stage,
            "--to",
            "render",
            *(["--resume"] if args.resume else []),
            *(["--dry-run"] if args.dry_run else []),
            *(["--state-db", args.state_db] if args.state_db else []),
        ]
    )
    return run_pipeline(run_args)


def _review_command(args: argparse.Namespace) -> int:
    project_json = Path(args.project_json).resolve()
    commands = [
        [sys.executable, str(ROOT / "scripts" / "apply_review_decisions.py"), "--project-json", str(project_json)],
        [sys.executable, str(ROOT / "scripts" / "build_regeneration_plan.py"), "--project-json", str(project_json)],
        [sys.executable, str(ROOT / "scripts" / "build_production_report.py"), "--project-json", str(project_json)],
    ]
    if args.dry_run:
        for cmd in commands:
            print("DRY-RUN:", " ".join(cmd))
    else:
        for cmd in commands:
            subprocess.run(cmd, check=True)
    dashboard = build_project_status(project_json, state_db_override=args.state_db or None)
    print(format_project_status(dashboard, include_failed=args.failed))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yt-nonstop")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run pipeline stages through the package orchestrator.")
    stage_choices = STAGE_SEQUENCE + ["generate_fastgen_prompts", "scene_context_pack", "production_report"]
    run_parser.add_argument("--project-json", required=True)
    run_parser.add_argument("--from", dest="from_stage", choices=stage_choices)
    run_parser.add_argument("--to", dest="to_stage", choices=stage_choices, default="render")
    run_parser.add_argument("--resume", action="store_true")
    run_parser.add_argument("--retry-failed-only", action="store_true")
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--render-dry-run", action="store_true")
    run_parser.add_argument("--state-db", default="")
    run_parser.add_argument("--profile", default="")
    run_parser.add_argument("--real-generation", action="store_true")
    run_parser.add_argument("--limit-frames", type=int, default=0)
    run_parser.add_argument("--auto-author-llm", dest="auto_author_llm", action="store_true")
    run_parser.add_argument("--no-auto-author-llm", dest="auto_author_llm", action="store_false")
    run_parser.add_argument("--require-filled-prompts", action="store_true")
    run_parser.add_argument("--image-size", default="1024x1024")
    run_parser.add_argument("--reference-image-size", default="1024x1536")
    run_parser.add_argument("--reference-aspect-ratio", default="2:3")
    run_parser.add_argument("--concurrency", type=int, default=10)
    run_parser.add_argument("--reference-concurrency", type=int, default=10)
    run_parser.add_argument("--poll-seconds", type=float, default=3.0)
    run_parser.add_argument("--max-polls", type=int, default=120)
    run_parser.add_argument("--width", type=int, default=1920)
    run_parser.add_argument("--height", type=int, default=1080)
    run_parser.add_argument("--image-retry-rounds", type=int, default=3)
    run_parser.add_argument("--soften-policy-prompts", action="store_true")
    run_parser.set_defaults(auto_author_llm=True)
    run_parser.set_defaults(func=lambda args: run_pipeline(args))

    status_parser = subparsers.add_parser("status", help="Show operator dashboard.")
    status_parser.add_argument("--project-json", required=True)
    status_parser.add_argument("--stage", default="generate_images")
    status_parser.add_argument("--state-db", default="")
    status_parser.add_argument("--failed", action="store_true")
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=_status_command)

    validate_parser = subparsers.add_parser("validate", help="Validate one stage or the whole project.")
    validate_parser.add_argument("--project-json", required=True)
    validate_parser.add_argument("--stage", default="all", choices=STAGE_CHOICES)
    validate_parser.set_defaults(func=_validate_command)

    render_parser = subparsers.add_parser("render", help="Build timeline/render outputs through the package orchestrator.")
    render_parser.add_argument("--project-json", required=True)
    render_parser.add_argument("--from-stage", choices=["timeline", "render"], default="")
    render_parser.add_argument("--resume", action="store_true")
    render_parser.add_argument("--dry-run", action="store_true")
    render_parser.add_argument("--state-db", default="")
    render_parser.set_defaults(func=_render_command)

    review_parser = subparsers.add_parser("review", help="Apply review decisions and show current blockers.")
    review_parser.add_argument("--project-json", required=True)
    review_parser.add_argument("--state-db", default="")
    review_parser.add_argument("--failed", action="store_true")
    review_parser.add_argument("--dry-run", action="store_true")
    review_parser.set_defaults(func=_review_command)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    raise SystemExit(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    main()
