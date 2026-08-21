# AGENTS.md

## Tavern

Use `$HERMES_HOME/skills/creative/tavern/SKILL.md` only as the router for broad,
ambiguous, or cross-domain Tavern requests. For a specific request, load only
the matching specialist:

- `tavern-world`: create, find, import, localize, expand, or repair a world,
  character card, worldbook, user Persona, or opening.
- `tavern-world-visuals`: import world images and manage per-world visual themes.
- `tavern-story-profile`: recall stories and maintain durable story preferences
  and their bounded Hermes memory projection.
- `tavern-continuity`: diagnose or repair generation, compression, story ledger,
  runtime cast, prompt, or continuity problems.
- `tavern-ops`: configure models and operate, provision, verify, name, or localize
  Tavern Liveware.

Before changing Tavern state, follow
`$HERMES_HOME/skills/creative/tavern/references/shared-contract.md` and verify the
result. Preserve persistent worlds, user identity, credentials, sessions,
assets, starter content, and custom skills unless the user explicitly requests
that exact data change.

Use `$HERMES_HOME/skills/system/tavern-updater/SKILL.md` for release checks,
review, installation, and rollback. Never improvise `git pull` or directly
overwrite release-managed runtime, frontend, skill, or updater files.

Use `$HERMES_HOME/skills/system/model-api-manager/SKILL.md` to add, test, switch,
or repair model APIs for the Agent, Tavern, or both. Keep the two configuration
scopes separate and never expose credentials in commands, logs, or replies.

Start every update review through the verified updater Bootstrap:

```sh
curl -fsSL https://github.com/LoveMaker-art/noras-tavern/releases/latest/download/install-tavern-updater.sh | sh
```
