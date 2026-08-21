# Liveware Operations

## Paths

- Runtime: `$TAVERN_APP_DIR`
- State: `$TAVERN_STATE_DIR`
- App registration: `$TAVERN_STATE_DIR/apps.json`
- Maintained scripts: `$HERMES_HOME/skills/creative/tavern/scripts`

App IDs, domains, names, and credentials are instance state. Never copy them
into a reusable image, Skill, or release.

## Provision And Restart

```sh
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
sh "$HERMES_HOME/skills/creative/tavern/scripts/provision.sh"
sh "$HERMES_HOME/skills/creative/tavern/scripts/bringup.sh"
python3 "$HERMES_HOME/skills/creative/tavern/scripts/tavern_cli.py" doctor --json
```

`provision.sh` creates or reconciles Liveware registration. `bringup.sh` starts
the runtime, obtains required configuration through the maintained path, binds
the apps, and synchronizes the idempotent `gateway:startup` registration hook.
Do not manually extract keys, kill the server, or reconstruct its environment.

The first ClawChat greeting is controlled by `$HERMES_HOME/clawchat/greeting.md`.
Do not add a legacy first-greeting hook.

## Dynamic Identity

The runtime resolves current ClawChat identity metadata and exposes it through
`/api/identity`. Interface strings use generic fallback roles only when metadata
is unavailable. Do not hardcode a person's name into app titles or Skill text.

## Speech State

Generated speech cache lives under `$TAVERN_STATE_DIR/tts-cache`; clone
references live under `$TAVERN_STATE_DIR/tts-references`. Cache identity
includes normalized text and active voice settings. Cache hits refresh last-use
time; generated audio unused for the configured retention period may be removed.
Clone references are removed only through explicit clone deletion.

## Verification

Require local health, expected app registration, public reachability when
available, and stable process state. A Tavern-only failure does not justify a
Hermes gateway restart without evidence.
