---
name: auth-security-privacy
description: Review authentication, security, and privacy decisions for the yt_nonstop web app. Use when evaluating local-only trust boundaries, filesystem exposure, secret handling, operator permissions, and future multi-user hardening.
---

# Auth Security Privacy

## Repo Context

- Current studio is local-only and single-operator
- It can access local project folders and may launch provider-backed generation jobs
- Secrets may exist in local environment variables for image generation or other providers

## Workflow

1. Start from the current trust model and machine boundaries.
2. Identify all filesystem, secret, and subprocess surfaces.
3. Separate acceptable local-only shortcuts from unacceptable unsafe defaults.
4. Restrict path traversal, file reads, and write actions to known roots and approved commands.
5. Document what must change if the app ever becomes networked or multi-user.
6. Treat provider credentials, personal files, and generated media history as privacy-sensitive data.

## Inputs

- Current backend routes
- Filesystem access rules
- Environment-variable usage
- External integration points

## Outputs

- Security review notes
- Privacy and secrets guidance
- Hardening recommendations
- Future auth requirements if deployment scope expands

## Checklist

- Verify file access is rooted and controlled
- Verify secrets are never surfaced in UI payloads or logs
- Verify mutating actions are bounded to known commands
- Verify local-only assumptions are documented
- Verify future network deployment risks are called out early
