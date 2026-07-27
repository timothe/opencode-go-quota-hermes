# OpenCode Go Quota — Hermes plugin

Track **OpenCode Go** subscription windows (5-hour / weekly / monthly), warn when
a limit is near, optionally auto-block tools, and postpone work via Hermes cron.

This plugin is **OpenCode Go only**. It does not track OpenRouter, OpenCode Zen
billing, Cursor, or local `hermes insights` token counts.

There is **no official OpenCode Go usage API**. Quota is scraped from the
workspace dashboard (approach inspired by
[slkiser/opencode-quota](https://github.com/slkiser/opencode-quota), MIT).

## Install

```bash
hermes plugins install timothe/opencode-go-quota-hermes --enable
```

Hermes clones the repo (keeps `.git`, so later `hermes plugins update` works),
prompts for workspace ID and auth cookie, saves them to `~/.hermes/.env`, then
enables the plugin.

If you previously installed a subdirectory path (`…/opencode-go-quota`) and
`hermes plugins update` says “no .git directory”, force-reinstall once:

```bash
hermes plugins install timothe/opencode-go-quota-hermes --force --enable
```

Restart the gateway so hooks load:

```bash
hermes gateway restart
# or: hermes gateway stop && hermes gateway start
```

On the **first chat turn after that restart**, Hermes gets a short notice that
OpenCode Go quota monitoring is active and should tell you it’s in place.
Disable with `OPENCODE_GO_QUOTA_ANNOUNCE=false` if you don’t want that.

### Update

```bash
hermes plugins update opencode-go-quota
hermes gateway restart
```

## Getting your workspace ID and auth cookie

OpenCode Go does not expose quota on the API key. You need a signed-in browser
session cookie.

### 1. Workspace ID

1. Sign in at [https://opencode.ai/auth](https://opencode.ai/auth).
2. Open your **Go** usage page. The URL looks like:

   `https://opencode.ai/workspace/abc123xyz/go`

3. Copy only the middle segment (`abc123xyz`) — that is `OPENCODE_GO_WORKSPACE_ID`.
4. Do **not** paste the full URL or your API key.

### 2. Auth cookie

1. Stay signed in on [https://opencode.ai](https://opencode.ai).
2. Open DevTools:
   - **Chrome / Edge / Brave:** `F12` or right-click → Inspect → **Application**
   - **Firefox:** `F12` → **Storage**
3. Sidebar: **Cookies** → `https://opencode.ai`
4. Find the cookie named exactly **`auth`** (not other cookies).
5. Copy its **Value** (a long opaque string) into `OPENCODE_GO_AUTH_COOKIE`.

Tips:

- Cookie expires when you sign out or after idle time. If checks start failing,
  re-copy `auth` and update `~/.hermes/.env`.
- Never commit the cookie to git or paste it into public chats.
- `OPENCODE_GO_API_KEY` is for inference only — it cannot read quota.

### Config file alternative

```json
// ~/.config/opencode/opencode-quota/opencode-go.json
{ "workspaceId": "...", "authCookie": "..." }
```

Environment variables override the file.

## Asking for quota (natural language)

Simply ask Hermes:

- "What's my current quota?"
- "How much OpenCode Go do I have left?"
- "Am I close to hitting the Go limit?"

You can also run slash **`/go-quota`** (or `/go-quota refresh`).

Expect a spoken answer, for example:

> Your OpenCode Go quota is looking good for now: 100% remaining on the 5-hour
> window (resets in about 5 hours), 100% remaining on the weekly window
> (resets in about 6 days), and about 50% remaining on the monthly window
> (resets on the 14th).

## What this plugin registers

| Surface | Name | Purpose |
| --- | --- | --- |
| Tool | `opencode_go_quota_check` | Fetch Go quota; returns natural-language summary for the model |
| Slash | `/go-quota` | Same summary on demand |
| Skill | `opencode-go-quota` | Postpone-via-cron playbook |
| Hook | `pre_llm_call` | Warn when low; announce once per process; answer NL quota asks inline (bypasses Tool Search deferral) |
| Hook | `pre_tool_call` | Optional hard block when critically low |

### Avoiding conflicts with other skills/plugins

| Prefer this plugin when… | Prefer something else when… |
| --- | --- |
| Question is about **OpenCode Go** plan windows | OpenRouter credits → OpenRouter usage API / other plugin |
| Model provider is `opencode-go` | Zen **billing/balance** → separate Zen tooling |
| User says “my quota” while on Go | Local token stats → `hermes insights` |

Names are intentionally prefixed (`opencode_go_…`, `/go-quota`, skill
`opencode-go-quota`) so they don’t collide with a generic `/quota` or
`provider-usage-tracking`. If both skills are enabled, use **this** one for Go.

## Optional env

```bash
OPENCODE_GO_QUOTA_WARN=20            # % remaining → warn (default 20)
OPENCODE_GO_QUOTA_CRITICAL=5         # % remaining → critical (default 5)
OPENCODE_GO_QUOTA_AUTO_BLOCK=true    # block non-allowlisted tools when critical
OPENCODE_GO_QUOTA_ANNOUNCE=false     # skip first-turn “plugin is active” notice
# OPENCODE_GO_QUOTA_BLOCK_ALLOWLIST=opencode_go_quota_check,cronjob,memory,session_search,skill_view,skills_list,todo
```

Allowlisted tools still run under auto-block so Hermes can check quota and
schedule a `cronjob` after reset.

## After install — is it working?

1. `hermes plugins list` — `opencode-go-quota` should show **enabled**.
2. Confirm it actually loads (important):

   ```bash
   rg "opencode-go-quota" ~/.hermes/logs/errors.log | tail
   ```

   You should **not** see `Failed to load plugin 'opencode-go-quota'`.
3. Restart the gateway, then send any chat message — on the **first turn of that
   new process** Hermes should mention quota monitoring is in place.
4. Ask: **"What's my current quota?"** — expect tool `opencode_go_quota_check`,
   not skill `provider-usage-tracking`.
5. Try slash **`/go-quota`**. If you get `Unknown command`, the plugin did not
   load — check the log line above and re-run `hermes plugins update` / reinstall.

### If Hermes still opens `provider-usage-tracking`

That bundled skill wrongly says OpenCode Go has no API. This plugin’s
`pre_llm_call` hook intercepts quota questions, fetches quota itself, and
injects the answer into context (so it still works when Hermes Tool Search
has deferred `opencode_go_quota_check`). After updating, restart the gateway.

## Develop / test

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pytest
pytest -q
```

No live network or cookies required for unit tests.

## License

MIT. Dashboard scrape logic adapted from OpenCode Quota (MIT).
