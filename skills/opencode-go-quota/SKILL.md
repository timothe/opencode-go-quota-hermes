---
name: opencode-go-quota
description: >
  PREFERRED for OpenCode Go remaining quota / allowance / rate limits / pace,
  and Zen balance / Use-balance-after-Go-limits.
  Use when the user asks "What's my current quota?", "remaining balance on
  OpenCode Go", or similar. Calls tool opencode_go_quota_check.
  Do NOT use provider-usage-tracking for OpenCode Go.
version: 0.2.0
tags: [opencode-go, quota, balance, allowance, rate-limit, cron, postpone]
---

# OpenCode Go Quota

This skill is **scoped to OpenCode Go** (`opencode.ai` Go plan windows) plus
**Zen balance as Go overage fallback** (Use-balance-after-Go-limits).
It does **not** replace OpenRouter usage or `hermes insights`.

OpenCode Go has **no official usage API**. The plugin scrapes the workspace
`/go` and `/billing` dashboards and exposes tool `opencode_go_quota_check`,
slash `/go-quota`, and slash `/go-balance`.

## How the user asks (natural)

Simply ask Hermes in chat:

- "What's my current quota?"
- "How much OpenCode Go do I have left?"
- "Am I ahead of pace this week?"
- "What's my remaining balance on OpenCode Go?"
- "Is use-balance-after-limits enabled?"

You should call `opencode_go_quota_check` (or use `balance=true` for balance-only)
and **relay the natural-language summary**. Do not dump ISO timestamps or raw
JSON unless they explicitly ask for machine output.

Summaries include **pace advice** (linear burn vs elapsed window time) and,
when enough local history exists, **trend vs recent burn**.

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
- `OPENCODE_GO_QUOTA_ANNOUNCE=false` — disable once-ever first-install notice

## Avoiding conflicts

| This plugin | Not this plugin |
| --- | --- |
| Tool `opencode_go_quota_check` | Generic `quota_check` from other sources |
| Slash `/go-quota`, `/go-balance` | Other providers' `/quota` |
| Skill `opencode-go-quota` | `provider-usage-tracking` (dashboard-only notes) |

If both skills are enabled, prefer **this** skill for OpenCode Go questions.

## Workflow

1. Call `opencode_go_quota_check` (use `force=true` after errors; `balance=true` for balance-only).
2. Tell the user the prose summary (pace / remaining / balance + useBalance).
3. If getting low, critical, or ahead of pace:
   - Propose postpone via Hermes `cronjob` after the tightest window resets.
   - Continue now only if the user opts in (fallback provider, Zen balance if enabled, or accept burn).
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
