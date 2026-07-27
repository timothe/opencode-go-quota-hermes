---
name: opencode-go-quota
description: >
  Check OpenCode Go quota (5h / weekly / monthly), flag when near a limit,
  and postpone work via cron until the window resets.
version: 0.1.0
tags: [opencode, quota, billing, rate-limit, cron, postpone]
---

# OpenCode Go Quota

OpenCode Go has **no official usage API**. This plugin scrapes the workspace
dashboard and exposes `quota_check` / `/quota`.

Auth (set at `hermes plugins install` or in `~/.hermes/.env`):

- `OPENCODE_GO_WORKSPACE_ID` — from `https://opencode.ai/workspace/{id}/go`
- `OPENCODE_GO_AUTH_COOKIE` — browser `auth` cookie for `opencode.ai`

Optional:

- `OPENCODE_GO_QUOTA_WARN` (default `20`) — % remaining → warn
- `OPENCODE_GO_QUOTA_CRITICAL` (default `5`) — % remaining → critical
- `OPENCODE_GO_QUOTA_AUTO_BLOCK=true` — hard-block tools when critical

**API key ≠ quota.** `OPENCODE_GO_API_KEY` does not expose limits.

## When to use

- Before long / expensive tasks on OpenCode Go
- After 429 / quota / rate-limit errors
- When the plugin injects an `[OpenCode Go quota]` warn into the turn
- User asks about remaining Go allowance

## Workflow

1. Call tool `quota_check` (or slash `/quota`). Prefer `force=true` after errors.
2. Read `status`: `ok` | `warn` | `critical` | `incomplete` | `error`.
3. If `warn` or `critical`:
   - Tell the user which window(s), remaining %, and `soonest_reset_at`.
   - **Propose postpone:** create a Hermes `cronjob` scheduled at/after reset
     with the deferred task prompt. Do not burn remaining quota on non-urgent work.
   - Continue now only if the user opts in (fallback provider, or accept burn).
4. If `incomplete` / `error`: ask user to refresh the `auth` cookie (it expires).

## Postpone via cron (example)

```text
cronjob(
  action="create",
  name="Resume after Go quota reset",
  schedule="<ISO or cron at/after soonest_reset_at>",
  prompt="<original deferred task>"
)
```

Allowlisted tools still run under auto-block (`quota_check`, `cronjob`, memory/skill tools)
so you can always schedule the resume.

## Pitfalls

1. Cookie expiry → scrape fails; re-copy `auth` from DevTools.
2. Local `hermes insights` ≠ subscription limits.
3. Billing (Zen balance) is separate; this skill covers Go quota windows only.
