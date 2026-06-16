---
name: backend-api-contract
description: Define and review the backend API contract for the yt_nonstop web studio. Use when designing FastAPI endpoints, payload shapes, action semantics, validation boundaries, and frontend-backend integration rules.
---

# Backend API Contract

## Repo Context

- Backend web layer lives in `src/yt_nonstop/webapi/`
- Current backend wraps CLI commands and existing artifacts
- API must stay local-operator friendly and avoid inventing a second pipeline model

## Workflow

1. Inspect existing endpoints and models first.
2. Design payloads around operator use cases: discovery, state, jobs, review, assets, actions.
3. Keep endpoint semantics explicit, especially for write-heavy job launches.
4. Distinguish read-only queries from job-triggering commands.
5. Prefer stable typed models over ad hoc nested blobs where product-critical data is consumed by the frontend.
6. Document compatibility rules when evolving existing endpoints.

## Inputs

- Existing FastAPI routes and Pydantic models
- Frontend data requirements
- CLI command boundaries
- Job orchestration rules

## Outputs

- Endpoint contract changes
- Request and response shapes
- Validation and error-handling guidance
- Compatibility notes for frontend consumers

## Checklist

- Verify every mutating endpoint launches a bounded CLI action
- Verify payloads expose operator-relevant state, not raw internal noise
- Verify project-scoped and global job views are consistent
- Verify limited-support project behavior is explicit
- Verify contract changes do not silently break existing pages
