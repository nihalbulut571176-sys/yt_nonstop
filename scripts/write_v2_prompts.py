import argparse

from v2_pipeline_lib import write_v2_prompts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()
    print(write_v2_prompts(args.project_json))


if __name__ == "__main__":
    main()
