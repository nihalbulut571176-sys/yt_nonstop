from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from yt_nonstop.pipeline.pilot_profiles import active_profile_name, effective_limit_frames, resolve_runtime_profile  # noqa: E402
from yt_nonstop.pipeline.project_config import load_project  # noqa: E402
from yt_nonstop.pipeline.real_generation_preflight import run_real_generation_preflight  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    parser.add_argument("--profile", default="")
    parser.add_argument("--limit-frames", type=int, default=0)
    parser.add_argument("--real-generation", action="store_true")
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    profile_name = active_profile_name(project, args.profile)
    profile = resolve_runtime_profile(profile_name)
    limit_frames = effective_limit_frames(project, args.limit_frames, profile)
    result = run_real_generation_preflight(
        project_json=project_json,
        project=project,
        profile=profile,
        real_generation=args.real_generation,
        limit_frames=limit_frames,
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
