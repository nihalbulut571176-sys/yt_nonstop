---
name: frontend-ui-ux-system
description: Design and refine the frontend UI system for the yt_nonstop web studio. Use when shaping layouts, navigation, operator dashboards, visual hierarchy, and interaction patterns for local production workflows.
---

# Frontend UI UX System

## Repo Context

- Current SPA lives in `web/app/`
- Current screens: `Projects`, `Pipeline`, `Review`, `Assets`
- Users are operators running long-lived local workflows, not casual end users

## Workflow

1. Start from operator tasks, not decorative UI.
2. Design for fast scanning: current project, current stage, blockers, active job, recent outputs.
3. Favor dense but readable layouts over public-marketing patterns.
4. Separate recommended actions from advanced controls.
5. Ensure limited-support projects are visually honest about restrictions.
6. Keep artifact previews and review context easy to jump to from pipeline state.

## Inputs

- Current page structure
- Backend payloads
- Operator scenarios
- Existing design direction in `web/app/src/styles.css`

## Outputs

- Page-level UX recommendations
- Component and state-view patterns
- Interaction rules for errors, disabled states, and loading
- Visual hierarchy guidance for operator flows

## Checklist

- Verify primary actions are visible without digging
- Verify errors and blockers are actionable
- Verify limited-support versus full-support states are differentiated
- Verify tables and logs remain readable on desktop and laptop widths
- Verify the UI favors production speed over feature clutter
