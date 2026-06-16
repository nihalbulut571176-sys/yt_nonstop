---
name: external-integrations-mcp
description: Plan and review external integrations for yt_nonstop, including provider APIs, MCP-style tooling, local connectors, and browser or automation surfaces. Use when integrating external services while keeping the core workflow stable and auditable.
---

# External Integrations MCP

## Repo Context

- The workflow already depends on external generation providers and local tool surfaces
- Web and automation layers must not hide integration boundaries
- Operator trust depends on clear provider behavior, retries, and failure visibility

## Workflow

1. Inventory the current external touchpoints first.
2. Define clear adapter boundaries between internal workflow logic and external systems.
3. Keep secrets, retries, and timeouts explicit.
4. Ensure external failures degrade visibly and safely for operators.
5. Distinguish repo-owned contracts from provider-specific payload details.
6. Document which integrations are core, optional, experimental, or local-only.

## Inputs

- Provider modules and env vars
- Local browser or MCP surfaces
- Job orchestration needs
- Integration-specific failure modes

## Outputs

- Integration boundary design
- Adapter recommendations
- Retry/error-handling guidance
- Security and observability notes for external systems

## Checklist

- Verify provider-specific logic is isolated
- Verify secrets and tokens stay out of UI and logs
- Verify retries and fallbacks are explicit
- Verify operator-facing failure states remain understandable
- Verify experimental integrations are labeled as such
