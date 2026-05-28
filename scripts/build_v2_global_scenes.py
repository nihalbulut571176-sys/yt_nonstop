import argparse

from v2_pipeline_lib import build_v2_global_scenes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--target-scenes", type=int)
    args = parser.parse_args()
    print(build_v2_global_scenes(args.project_json, target_scenes=args.target_scenes))


if __name__ == "__main__":
    main()
