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

Liveware app IDs, names, and domains are instance state stored in
`/opt/data/tavern-state/apps.json`. Do not copy them into documentation or a
release image intended for another owner.

Operational boundaries:

- `provision.sh` creates or reuses liveware apps and registers them with ClawChat.
- `bringup.sh` starts the tavern server and binds both liveware apps to the local server.
- Runtime state must stay in `/opt/data/tavern-state`, not inside the skill package.
- `SOUL.md` remains `/opt/data/SOUL.md`; do not put persona files in the skill.
- First ClawChat greeting is controlled by `/opt/data/clawchat/greeting.md`; do not add a legacy first-greeting hook.

## Name Change Synchronization

The runtime reads the current ClawChat agent nickname from platform metadata and
exposes the resolved identity through `/api/identity`. The web i18n layer applies
that identity at runtime. Generic values such as `主理人` and `Curator` are
fallback roles for environments where platform metadata is unavailable; they are
not owner profile data.

Liveware registration names and app IDs remain instance state in `apps.json`.
After changing registration metadata, run `provision.sh` to reconcile ClawChat
registration, then `bringup.sh` to bind the current apps.

The current ClawChat plugin reads a user-editable activation greeting prompt from:

```
/opt/data/clawchat/greeting.md
```

This file is a prompt to Hermes, not a literal message template. It should instruct the story curator to send one normal chat reply that clearly explains who she is, what she can help with, where to open the Liveware tavern (`the Tavern`), and that the user can ask her any usage question.

Do not add a first-greeting hook; the old hook implementation caused duplicate openers and has been removed.

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
curl -fsS https://<app-domain>/api/health
```

The Hermes terminal tool forbids `&` backgrounding in foreground mode — use `terminal(background=true)` for the restart command.
