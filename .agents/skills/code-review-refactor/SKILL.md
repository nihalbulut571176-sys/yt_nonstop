---
name: code-review-refactor
description: Review and refactor yt_nonstop code with focus on workflow correctness, maintainability, and operator safety. Use when auditing technical debt, simplifying orchestration logic, or preparing code for larger web-app evolution.
---

# Code Review Refactor

## Repo Context

- The repo mixes CLI workflow logic, local project conventions, and a growing web layer
- Regressions in timing, job launching, or file handling can break expensive operator flows

## Workflow

1. Review behavior first, not style first.
2. Identify code paths that are now duplicated between CLI, status, and web surfaces.
3. Separate safe refactors from product-affecting behavior changes.
4. Prefer consolidation around canonical helpers and typed models.
5. Call out risky coupling between project artifacts, runtime state, and UI assumptions.
6. Recommend refactors that reduce operator risk and future web complexity.

## Inputs

- Current implementation slice
- Bug report or refactor goal
- Existing tests and failure modes
- Product constraints

## Outputs

- Review findings
- Refactor strategy
- Risk and regression notes
- Suggested follow-up tests

## Checklist

- Verify review findings prioritize correctness and regressions
- Verify refactors reduce duplication or ambiguity
- Verify changes preserve canonical workflow behavior
- Verify risky assumptions are made explicit
- Verify follow-up tests cover the changed behavior
