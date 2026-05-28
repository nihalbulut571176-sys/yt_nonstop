import argparse

from v2_pipeline_lib import export_v2_generator_queue


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()
    print(export_v2_generator_queue(args.project_json))


if __name__ == "__main__":
    main()
