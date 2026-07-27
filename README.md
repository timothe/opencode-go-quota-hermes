# OpenCode Go Quota — Hermes plugin

Track **OpenCode Go** subscription windows (5-hour / weekly / monthly), warn when
a limit is near, give **pace-aware** advice, optionally auto-block tools, and
postpone work via Hermes cron. Also reports **Zen balance** and whether
**Use-balance-after-Go-limits** is enabled (Go overage → Zen PAYG).

This plugin is **OpenCode Go–scoped**. Zen balance is included only as the
overage fallback for Go — it is not a full Zen billing manager. It does not
track OpenRouter, Cursor, or local `hermes insights` token counts.

There is **no official OpenCode Go usage API**. Quota is scraped from the
workspace `/go` dashboard; balance from `/billing` (same `auth` cookie).
Approach inspired by [slkiser/opencode-quota](https://github.com/slkiser/opencode-quota)
and [donrami/pi-go-bars](https://github.com/donrami/pi-go-bars) (MIT).

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

On the **first chat after a fresh install** (once ever), Hermes is nudged to
say quota monitoring is on. Restarts/updates do not re-announce. Disable with
`OPENCODE_GO_QUOTA_ANNOUNCE=false`. To re-test: delete
`~/.hermes/cache/opencode-go-quota-announced`.

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

## Asking for quota / balance (natural language)

Simply ask Hermes:

- "What's my current quota?"
- "How much OpenCode Go do I have left?"
- "Am I close to hitting the Go limit?"
- "What's my remaining balance on OpenCode Go?"
- "Is use balance after limits enabled?"

Slash commands:

- **`/go-quota`** (or `/go-quota refresh`) — windows + pace (+ balance line)
- **`/go-balance`** — Zen balance + Use-balance-after-Go-limits only

Expect spoken answers that include remaining windows, whether burn is ahead of
linear pace (e.g. 18% weekly after one day), and Zen balance when available.

## Pace advice and local history

Each successful live fetch appends a compact sample to
`~/.hermes/cache/opencode-go-quota-history.jsonl` (no cookie / workspace id).
Samples are deduped within an hour and retained for 90 days.

- **Day one:** advice uses linear pace from `reset_in_sec` vs assumed window
  lengths (5h / 7d / 30d) — no history required.
- **After a few days:** trend advice can say burn is faster/slower than your
  recent average within the current window cycle.

## What this plugin registers

| Surface | Name | Purpose |
| --- | --- | --- |
| Tool | `opencode_go_quota_check` | Fetch Go quota (+ optional `balance=true`); natural-language summary |
| Slash | `/go-quota` | Quota + pace (+ balance line) |
| Slash | `/go-balance` | Zen balance + useBalance toggle |
| Skill | `opencode-go-quota` | Postpone-via-cron playbook |
| Hook | `pre_llm_call` | Warn when low; once-ever first-install notice; answer NL quota/balance asks inline |
| Hook | `pre_tool_call` | Optional hard block when critically low |

### Avoiding conflicts with other skills/plugins

| Prefer this plugin when… | Prefer something else when… |
| --- | --- |
| Question is about **OpenCode Go** plan windows or Go overage Zen balance | OpenRouter credits → OpenRouter usage API / other plugin |
| Model provider is `opencode-go` | Full Zen account management beyond Go overage |
| User says “my quota” / “Go balance” while on Go | Local token stats → `hermes insights` |

Names are intentionally prefixed (`opencode_go_…`, `/go-quota`, `/go-balance`,
skill `opencode-go-quota`) so they don’t collide with a generic `/quota` or
`provider-usage-tracking`. If both skills are enabled, use **this** one for Go.

## Optional env

```bash
OPENCODE_GO_QUOTA_WARN=20            # % remaining → warn (default 20)
OPENCODE_GO_QUOTA_CRITICAL=5         # % remaining → critical (default 5)
OPENCODE_GO_QUOTA_AUTO_BLOCK=true    # block non-allowlisted tools when critical
OPENCODE_GO_QUOTA_ANNOUNCE=false     # skip once-ever first-install notice
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
3. Ask: **"What's my current quota?"** — expect a paced remaining-windows answer.
4. Ask: **"What's my remaining balance on OpenCode Go?"** — expect Zen $ + useBalance.
5. Try slash **`/go-quota`** and **`/go-balance`**. If you get `Unknown command`,
   the plugin did not load — check the log line above and re-run
   `hermes plugins update` / reinstall.

### If Hermes still opens `provider-usage-tracking`

That bundled skill wrongly says OpenCode Go has no API. This plugin’s
`pre_llm_call` hook intercepts quota/balance questions, fetches data itself, and
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

MIT. Dashboard scrape logic adapted from OpenCode Quota / pi-go-bars (MIT).
