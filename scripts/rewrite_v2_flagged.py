import argparse

from v2_pipeline_lib import rewrite_v2_flagged


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()
    print(rewrite_v2_flagged(args.project_json))


if __name__ == "__main__":
    main()
