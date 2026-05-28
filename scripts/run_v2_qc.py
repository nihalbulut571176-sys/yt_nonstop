import argparse

from v2_pipeline_lib import run_v2_qc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--similarity-threshold", type=int, default=85)
    args = parser.parse_args()
    print(run_v2_qc(args.project_json, similarity_threshold=args.similarity_threshold))


if __name__ == "__main__":
    main()
