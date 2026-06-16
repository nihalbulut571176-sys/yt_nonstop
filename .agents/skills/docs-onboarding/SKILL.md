---
name: docs-onboarding
description: Create and maintain onboarding and operator documentation for yt_nonstop. Use when documenting repo truth, workspace conventions, runbooks, feature behavior, architecture, and how new engineers or operators should work with the system.
---

# Docs Onboarding

## Repo Context

- Repo truth is `yt_nonstop`
- Heavy project outputs live in `YT_visual`
- Current docs already cover workflow, workspace, audit, web prototype, and web studio

## Workflow

1. Start from what a new engineer or operator actually needs on day one.
2. Keep repo truth, workspace truth, and generated-output truth separate.
3. Update docs when behavior changes, not only when code changes a lot.
4. Prefer small high-signal docs over sprawling documentation trees.
5. Make run commands, constraints, and non-goals easy to find.
6. Note what is intentionally local-only or intentionally not committed.

## Inputs

- Current repo docs
- Changed behavior or new features
- Operator confusion points
- Setup and run requirements

## Outputs

- Updated onboarding docs
- Architecture summaries
- Runbooks and feature docs
- Explicit assumptions and limitations

## Checklist

- Verify source-of-truth locations are clear
- Verify startup/run instructions are correct
- Verify non-goals and limitations are documented
- Verify docs match real behavior, not aspirational behavior
- Verify a new teammate could answer “where is the code, where is the data, how do I run it?”
