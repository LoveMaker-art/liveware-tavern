# Tavern Text Model Configuration

Tavern already owns its model registry through `tavern-ops`. Do not recreate
that registry in this skill.

```sh
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
CLI="$HERMES_HOME/skills/creative/tavern/scripts/tavern_cli.py"
python3 "$CLI" model list --json
python3 "$CLI" model test [name] --json
python3 "$CLI" model add <name> --base <url> --model <id> --key <key> --json
python3 "$CLI" model use <name> --json
python3 "$CLI" doctor --json
```

The helper calls Tavern's local event API so a secret is not exposed in process
arguments. `model add` tests before saving and makes the new configuration the
active Tavern text model.

The active Tavern model is global for story generation. It does not change the
Hermes Agent model, TTS model, or the independently managed story-ledger model.
Frontend model selection cannot create missing server credentials.

Tavern requires OpenAI-compatible Chat Completions. Tool calling is not required
for story generation, so its probe is intentionally different from the agent
probe.
