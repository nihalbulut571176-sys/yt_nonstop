# Branch Integration Report

Date: `2026-05-27`
Target branch: `codex/python-codex-fastgen-director`

## Goal

Rebuild the strongest working version of the YouTube documentary pipeline by combining:

- Python as the structural supervisor
- Codex/LLM as the prompt director for FastGen
- newer motion, QC, retry, and render tooling from later branches

## Branch review

### `codex/add-agents-production-pipeline`

Strongest ideas:

- SRT-first stage runner with explicit pipeline sequencing
- Python-managed project manifest and validation
- internal LLM authoring stage for FastGen prompts
- scene QA, prompt QA, continuity, style bible, context pack, and final review stages
- workflow docs for project-aware documentary production

Files adopted from this branch:

- `scripts/run_youtube_documentary_workflow.py`
- `scripts/run_fastgen_only_project.py`
- `scripts/auto_author_llm_prompts.py`
- `scripts/apply_llm_prompt_drafts.py`
- `scripts/run_scene_qa.py`
- `scripts/run_prompt_qa.py`
- `scripts/validate_project.py`
- `scripts/project_pipeline_utils.py`
- `scripts/build_project_*` LLM-first planning stack
- `agents/`
- `workflow/`

Why it matters:

This is the branch that restores the desired `Python + Codex internal LLM` loop instead of treating prompt writing as a manual chat-only step.

### `codex/word-align-llm-fastgen-v2`

Strongest ideas:

- hardened semantic prompt pipeline
- stronger continuity and prompt logic than early FastGen-only branches

How it was used:

- treated as the maturity baseline that informed the later animation branch

### `codex/youtube-autopipeline-workflow`

Strongest ideas:

- same hardened semantic direction as `word-align-llm-fastgen-v2`
- improved end-to-end workflow framing

How it was used:

- treated as equivalent to the semantic-pipeline hardening line

### `codex/veononstop-animation-pipeline`

Strongest ideas:

- latest technical base
- motion plan and QC-related project paths
- CSV/export utilities
- retry/test/render helpers
- mixed render support and more mature image/video orchestration

Why it was chosen as the base:

It is the newest branch and already contains the later production support utilities that we do not want to lose.

## Integration decision

The new branch starts from:

- `codex/veononstop-animation-pipeline`

Then layers in:

- the LLM-first SRT-first planning stack from `codex/add-agents-production-pipeline`

## Resulting workflow

1. Python validates inputs, `.env`, audio, SRT, and project structure.
2. Python builds scene timing and planning artifacts from transcript/SRT.
3. Python prepares prompt packages, continuity context, and QA checkpoints.
4. Codex/LLM writes FastGen prompt drafts inside the pipeline.
5. Python audits and validates those prompts before export.
6. Python exports generator-ready FastGen prompts and keeps render/retry utilities from the newer branches.

## Important behavioral choice

`scripts/run_fastgen_only_project.py` now defaults to the internal LLM authoring pass being enabled.

Default behavior:

- Python manages structure and audit
- Codex/LLM authors FastGen prompt drafts

Manual override:

- use `--no-auto-author-llm` if you want to bypass that stage and provide drafts yourself

## Recommended next execution path

Primary entrypoint:

- `python scripts/run_youtube_documentary_workflow.py --project-id <id> --audio-source <file> --raw-text-path <file>`

Direct runner:

- `python scripts/run_fastgen_only_project.py --project-json <project.json>`

## Notes

- `pytest` is not installed in the current Python environment, so unit verification was run with `python tests/test_prompt_pipeline.py`.
- Python source compilation passed with `compileall`.
