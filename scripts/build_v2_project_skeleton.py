import argparse

from v2_pipeline_lib import build_v2_project_skeleton


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()
    print(build_v2_project_skeleton(args.project_json))


if __name__ == "__main__":
    main()
