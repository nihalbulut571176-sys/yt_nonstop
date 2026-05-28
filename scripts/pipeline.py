import argparse
from pathlib import Path

from v2_pipeline_lib import (
    build_v2_global_scenes,
    build_v2_project_skeleton,
    build_v2_storyboard,
    build_v2_subscenes,
    export_v2_edit_timeline,
    export_v2_generator_queue,
    make_v2_test_batch,
    rewrite_v2_flagged,
    run_v2_directors_cut,
    run_v2_qc,
    write_v2_prompts,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_srt = subparsers.add_parser("parse-srt")
    parse_srt.add_argument("--project-json", required=True)

    build_scenes = subparsers.add_parser("build-scenes")
    build_scenes.add_argument("--project-json", required=True)
    build_scenes.add_argument("--target-scenes", type=int)

    build_subscenes = subparsers.add_parser("build-subscenes")
    build_subscenes.add_argument("--project-json", required=True)

    build_storyboard = subparsers.add_parser("build-storyboard")
    build_storyboard.add_argument("--project-json", required=True)

    directors_cut = subparsers.add_parser("directors-cut")
    directors_cut.add_argument("--project-json", required=True)
    directors_cut.add_argument("--chunk-size", type=int)

    write_prompts = subparsers.add_parser("write-prompts")
    write_prompts.add_argument("--project-json", required=True)

    qc = subparsers.add_parser("qc")
    qc.add_argument("--project-json", required=True)
    qc.add_argument("--similarity-threshold", type=int, default=85)

    rewrite_flagged = subparsers.add_parser("rewrite-flagged")
    rewrite_flagged.add_argument("--project-json", required=True)

    export_generator_queue = subparsers.add_parser("export-generator-queue")
    export_generator_queue.add_argument("--project-json", required=True)

    export_edit_timeline = subparsers.add_parser("export-edit-timeline")
    export_edit_timeline.add_argument("--project-json", required=True)

    make_test_batch = subparsers.add_parser("make-test-batch")
    make_test_batch.add_argument("--project-json", required=True)
    make_test_batch.add_argument("--count", type=int, default=30)

    args = parser.parse_args()
    project_json = Path(args.project_json).resolve()

    if args.command == "parse-srt":
        print(build_v2_project_skeleton(project_json))
    elif args.command == "build-scenes":
        print(build_v2_global_scenes(project_json, target_scenes=args.target_scenes))
    elif args.command == "build-subscenes":
        print(build_v2_subscenes(project_json))
    elif args.command == "build-storyboard":
        print(build_v2_storyboard(project_json))
    elif args.command == "directors-cut":
        print(run_v2_directors_cut(project_json, chunk_size=args.chunk_size))
    elif args.command == "write-prompts":
        print(write_v2_prompts(project_json))
    elif args.command == "qc":
        print(run_v2_qc(project_json, similarity_threshold=args.similarity_threshold))
    elif args.command == "rewrite-flagged":
        print(rewrite_v2_flagged(project_json))
    elif args.command == "export-generator-queue":
        print(export_v2_generator_queue(project_json))
    elif args.command == "export-edit-timeline":
        print(export_v2_edit_timeline(project_json))
    elif args.command == "make-test-batch":
        print(make_v2_test_batch(project_json, count=args.count))


if __name__ == "__main__":
    main()
