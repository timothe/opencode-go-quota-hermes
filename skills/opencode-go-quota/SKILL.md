---
name: opencode-go-quota
description: >
  PREFERRED for OpenCode Go remaining quota / allowance / rate limits / pace,
  and Zen balance / Use-balance-after-Go-limits.
  Use when the user asks "What's my current quota?", "remaining balance on
  OpenCode Go", or similar. Calls tool opencode_go_quota_check.
  Do NOT use provider-usage-tracking for OpenCode Go.
version: 0.4.0
tags: [opencode-go, quota, balance, allowance, rate-limit, cron, postpone]
---

# OpenCode Go Quota

This skill is **scoped to OpenCode Go** (`opencode.ai` Go plan windows) plus
**Zen balance as Go overage fallback** (Use-balance-after-Go-limits).
It does **not** replace OpenRouter usage or `hermes insights`.

Quota comes from the **official Go usage API** (`/zen/go/v1/usage`) using the Go
API key — no browser cookie needed. Zen balance reads the **console JSON APIs**
(`/console/api/billing/status`, `/console/api/go/status`) with the `auth` cookie
or a console bearer token. The plugin exposes tool `opencode_go_quota_check`,
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

- `OPENCODE_GO_API_KEY` — Go API key. **Quota source** (bearer token against
  `/zen/go/v1/usage`). No browser session needed.
- `OPENCODE_GO_AUTH_COOKIE` — browser cookie named `auth` on `opencode.ai`.
  **Zen balance source** (console JSON APIs).
- `OPENCODE_GO_CONSOLE_TOKEN` — optional console bearer token, used instead of
  the cookie when set. `OPENCODE_GO_ORG_ID` adds `x-org-id` for org-scoped logins.
- `OPENCODE_GO_WORKSPACE_ID` — only used by the deprecated dashboard-scrape
  fallback and to scope billing lookups.

Cookie walkthrough: see the plugin README ("Auth").

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
4. If the check fails: read the error. "usage API" → check `OPENCODE_GO_API_KEY`.
   Otherwise ask them to refresh the `auth` cookie.

## Maintenance — the console moved, the cookie is optional

opencode.ai migrated the console to a client-rendered SPA (`/console/*`), which
killed the old dashboard scrape: `/workspace/{id}/go` now 302s to
`/console/login` and the SSR usage markup is gone. Do not chase a fresh `auth`
cookie to fix a quota failure.

- **Quota source of truth:** `GET https://opencode.ai/zen/go/v1/usage` with
  `Authorization: Bearer $OPENCODE_GO_API_KEY`. Returns
  `usage.{rolling,weekly,monthly}` = `{status, percent, resetsAt}`; `percent` is
  *used*. Probe it first when quota breaks:
  `curl -s https://opencode.ai/zen/go/v1/usage -H "Authorization: Bearer $OPENCODE_GO_API_KEY"`.
  A 401 means the key, not the cookie.
- **Cookie only affects Zen balance.** Balance reads the console JSON APIs
  (`/console/api/billing/status`, `/console/api/billing/auto-recharge`,
  `/console/api/go/status`; microcents = dollars x 1e8). Those answer 401 for a
  stale cookie and 403 for the Go API key, so balance is always the cookie/token
  half. Balance failing is not a quota problem — quota still answers.
- **The console API** (`/console/api/go/status`) is also where `useBalance` and
  the Go window money meters live; it is member-scoped to the session.
- Any fix to plugin code is inert in a running gateway until `/restart`.

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
