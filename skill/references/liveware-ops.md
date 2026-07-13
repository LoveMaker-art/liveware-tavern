# Liveware Operations

Use this reference only for deployment, recovery, ClawChat liveware registration, tunnel binding, or uptime checks.

Paths:

- Skill: `/opt/data/skills/creative/tavern`
- Runtime app: `/opt/data/apps/tavern-runtime`
- State: `/opt/data/tavern-state`
- Compatibility link: `/opt/data/tavern -> /opt/data/apps/tavern-runtime`

Commands:

```sh
sh /opt/data/skills/creative/tavern/scripts/provision.sh
sh /opt/data/skills/creative/tavern/scripts/bringup.sh
curl -fsS http://127.0.0.1:8799/api/health
```

Liveware apps currently registered in `/opt/data/tavern-state/apps.json`:

- Console: `若棠的酒馆`
- Actor card: `若棠的故事档案`

Operational boundaries:

- `provision.sh` creates or reuses liveware apps and registers them with ClawChat.
- `bringup.sh` starts the tavern server and binds both liveware apps to the local server.
- Runtime state must stay in `/opt/data/tavern-state`, not inside the skill package.
- `SOUL.md` remains `/opt/data/SOUL.md`; do not put persona files in the skill.
- First ClawChat greeting is controlled by `/opt/data/clawchat/greeting.md`; do not restore the old `mo-first-greeting` hook.

## Name Change Synchronization

When Ruotang's ClawChat nickname changes, the name is **not** automatically propagated across the tavern system. The following locations contain hardcoded name references that must be updated manually:

| Layer | File | What to update |
|-------|------|---------------|
| Liveware registration | `tavern-state/apps.json` | `"name"` fields — then re-register via `clawchat_register_app` |
| HTML titles | `web/index.html`, `web/actor.html` | `<title>`, `<meta og:title>`, `<meta twitter:title>` |
| i18n strings | `web/i18n.js` | Both Chinese and English locales (~20 entries each) |
| Actor card | `server.py` (line ~250) | `"name"` field in actor card response |
| ClawChat deep link | `server.py` (line ~1657) | `/clawchat/<name>` path |
| AGENTS.md | `/opt/data/AGENTS.md` | App names and URLs in documentation |

The English transliteration (e.g., "Ruotang" for "若棠") is used in the i18n English locale and the ClawChat deep link path. It must match the current name.

Long-term fix direction: add an `ACTOR_NAME` constant in `server.py` that i18n and actor card read from, and have apps.json names fetched dynamically rather than hardcoded.

The current ClawChat plugin reads a user-editable activation greeting prompt from:

```
/opt/data/clawchat/greeting.md
```

This file is a prompt to Hermes, not a literal message template. It should instruct Ruotang to send one normal chat reply that clearly explains who she is, what she can help with, where to open the Liveware tavern (`Ruotang's Tavern`), and that the user can ask her any usage question.

Do not use `/opt/data/hooks/mo-first-greeting`; that old hook caused duplicate openers and has been removed.

## Server Restart

After modifying runtime code (server.py, app.js, console.css, i18n.js), restart the server.

The tavern server requires model credentials at startup. Use `bringup.sh` for the full restart (it auto-extracts the key from Hermes config). For a quick manual restart without re-binding liveware tunnels:

```sh
# Extract model key from Hermes config
KEY=$(python3 -c "
import yaml
with open('/opt/data/config.yaml') as f:
    c = yaml.safe_load(f)
p = c.get('providers', {}).get('clawling', {})
print(p.get('api_key', ''), p.get('base_url', ''))
")
API_KEY=$(echo "$KEY" | awk '{print $1}')
BASE_URL=$(echo "$KEY" | awk '{print $2}')

# Kill the running server and restart
kill $(pgrep -f "server.py --port 8799")
sleep 1
cd /opt/data/apps/tavern-runtime && \
  TAVERN_STATE_DIR=/opt/data/tavern-state \
  TAVERN_MODEL_KEY="$API_KEY" \
  TAVERN_MODEL_BASE="$BASE_URL" \
  /opt/hermes/.venv/bin/python server.py --port 8799 &
```

Verify key is loaded and both URLs work:

```sh
curl -fsS http://127.0.0.1:8799/api/health
curl -fsS https://app-7e523a668a44fff8.apps.clawling.io/api/health
```

The Hermes terminal tool forbids `&` backgrounding in foreground mode — use `terminal(background=true)` for the restart command.
