import argparse

from v2_pipeline_lib import run_v2_directors_cut


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--chunk-size", type=int)
    args = parser.parse_args()
    print(run_v2_directors_cut(args.project_json, chunk_size=args.chunk_size))


if __name__ == "__main__":
    main()
