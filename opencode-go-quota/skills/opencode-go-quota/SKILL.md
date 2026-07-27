---
name: opencode-go-quota
description: >
  OpenCode Go subscription quota only (5h / weekly / monthly). Use when the user
  asks naturally about Go allowance ("What's my current quota?", "How much Go
  do I have left?"), before long OpenCode Go tasks, or after Go 429/quota errors.
  Not for OpenRouter, Zen billing, or hermes insights.
version: 0.1.1
tags: [opencode-go, quota, rate-limit, cron, postpone]
---

# OpenCode Go Quota

This skill is **scoped to OpenCode Go** (`opencode.ai` Go plan windows).
It does **not** replace or conflict with OpenRouter usage, Zen billing, or
`hermes insights` (local token counts).

OpenCode Go has **no official usage API**. The plugin scrapes the workspace
dashboard and exposes tool `opencode_go_quota_check` and slash `/go-quota`.

## How the user asks (natural)

Simply ask Hermes in chat:

- "What's my current quota?"
- "How much OpenCode Go do I have left?"
- "Am I close to the Go limit?"

You should call `opencode_go_quota_check` and **relay the natural-language
summary** to the user. Do not dump ISO timestamps or raw JSON unless they
explicitly ask for machine output.

## Auth

Set at `hermes plugins install` or in `~/.hermes/.env`:

- `OPENCODE_GO_WORKSPACE_ID` — from `https://opencode.ai/workspace/{id}/go`
- `OPENCODE_GO_AUTH_COOKIE` — browser cookie named `auth` on `opencode.ai`

**API key ≠ quota.** `OPENCODE_GO_API_KEY` does not expose limits.

Cookie walkthrough: see the plugin README ("Getting your workspace ID and auth cookie").

## Optional env

- `OPENCODE_GO_QUOTA_WARN` (default `20`) — % remaining → warn
- `OPENCODE_GO_QUOTA_CRITICAL` (default `5`) — % remaining → critical
- `OPENCODE_GO_QUOTA_AUTO_BLOCK=true` — hard-block tools when critical
- `OPENCODE_GO_QUOTA_ANNOUNCE=false` — disable first-session “plugin is active” notice

## Avoiding conflicts

| This plugin | Not this plugin |
| --- | --- |
| Tool `opencode_go_quota_check` | Generic `quota_check` from other sources |
| Slash `/go-quota` | Other providers' `/quota` |
| Skill `opencode-go-quota` / `opencode-go-quota:opencode-go-quota` | `provider-usage-tracking` (dashboard-only notes) |

If both skills are enabled, prefer **this** skill for OpenCode Go questions.

## Workflow

1. Call `opencode_go_quota_check` (use `force=true` after errors).
2. Tell the user the prose summary (good / getting low / critically low + windows).
3. If getting low or critical:
   - Propose postpone via Hermes `cronjob` after the tightest window resets.
   - Continue now only if the user opts in (fallback provider, or accept burn).
4. If the check fails: ask them to refresh the `auth` cookie.

## Postpone via cron (example)

```text
cronjob(
  action="create",
  name="Resume after OpenCode Go quota reset",
  schedule="<after the soonest reset from the summary>",
  prompt="<original deferred task>"
)
```

Allowlisted tools still run under auto-block so you can always schedule the resume.
