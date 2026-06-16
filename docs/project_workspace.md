# Project Workspace Convention

## Rule

Each new narrated-video project gets its own dedicated folder.

A new project is defined by a new source audio file and a new narration text.

## Recommended Layout

```text
project_name/
  input/
    source_audio.mp3
    clean_script.txt
    atmosphere.txt
    youtube_package.txt
  work/
  images/
  output/
```

Optional subfolders may be added for focused experiments:

```text
project_name/
  first120/
  first15m/
  video/
  final_images/
  fastgen_first120/
```

## Folder Meanings

- `input/`: source materials and human-authored inputs
- `work/`: intermediate machine-readable outputs such as timelines, prompts, reports, and manifests
- `images/`: generated stills used by the pipeline
- `output/`: rendered videos and reviewable deliverables
- `final_images/`: clean export set that matches the final timeline and excludes stale or mixed historical images

## Hygiene Rules

- `images/` may contain mixed history during iteration
- `final_images/` should contain only the image files that match the current final timeline
- generated media should stay outside git by default
- large project folders should live in the local workspace, not in the repository

## Repo Relationship

The repository documents and powers the workflow.

The local workspace stores actual project runs.

Canonical repo:
- `C:\Users\MIKE\Documents\Codex\YT`

Canonical local workspace:
- `C:\Users\MIKE\Documents\Codex\YT_visual`
