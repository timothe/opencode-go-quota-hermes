# OpenCode Go Quota — Hermes plugin

Track OpenCode Go subscription windows (**5h / weekly / monthly**), warn when a
limit is near, optionally **auto-block** tools, and postpone work via Hermes cron.

There is **no official OpenCode Go usage API**. This plugin scrapes the workspace
dashboard (approach inspired by [slkiser/opencode-quota](https://github.com/slkiser/opencode-quota), MIT).

## Install (from a Hermes agent)

```bash
hermes plugins install timothe/opencode-go-quota-hermes/opencode-go-quota --enable
```

Install prompts for:

| Variable | Where to get it |
| --- | --- |
| `OPENCODE_GO_WORKSPACE_ID` | URL `https://opencode.ai/workspace/{id}/go` |
| `OPENCODE_GO_AUTH_COOKIE` | DevTools → Application → Cookies → `opencode.ai` → `auth` |

Values are saved to `~/.hermes/.env`.

**`OPENCODE_GO_API_KEY` is not enough** — inference keys do not expose quota.

## Usage

| Surface | What it does |
| --- | --- |
| Tool `quota_check` | JSON status for all windows |
| Slash `/quota` | Human summary (`/quota refresh` bypasses cache) |
| Skill `opencode-go-quota` | Postpone-via-cron playbook |
| Hook `pre_llm_call` | Injects a short warn when remaining ≤ warn threshold |
| Hook `pre_tool_call` | Optional hard block when critically low |

### Optional env

```bash
OPENCODE_GO_QUOTA_WARN=20          # % remaining → warn (default 20)
OPENCODE_GO_QUOTA_CRITICAL=5       # % remaining → critical (default 5)
OPENCODE_GO_QUOTA_AUTO_BLOCK=true  # block non-allowlisted tools when critical
# OPENCODE_GO_QUOTA_BLOCK_ALLOWLIST=quota_check,cronjob,memory,session_search,skill_view,skills_list,todo
```

Allowlisted tools still run under auto-block so you can call `quota_check` and
schedule a `cronjob` after reset.

### Config file alternative

```json
// ~/.config/opencode/opencode-quota/opencode-go.json
{ "workspaceId": "...", "authCookie": "..." }
```

Env vars override the file.

## Develop / test

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pytest
pytest -q
```

No live network or cookies required for unit tests.

## Layout

```text
opencode-go-quota/     # Hermes plugin (install this path)
  plugin.yaml
  __init__.py
  hooks.py
  tools.py
  quota/
  skills/opencode-go-quota/SKILL.md
tests/
```

## License

MIT. Dashboard scrape logic adapted from OpenCode Quota (MIT).
