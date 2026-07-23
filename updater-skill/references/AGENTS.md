# AGENTS.md

## Tavern Skills And Updates

Use `/opt/data/skills/creative/tavern/SKILL.md` as the lightweight router. Load only the matching specialist workflow:

- `tavern-world`: recommend, plan, create, expand, or rebuild a world, presenting compact ClawChat previews before approved writes.
- `tavern-world-visuals`: import durable world images and design, apply, inspect, or reset the story stage, top title bar, and right-side panel theme.
- `tavern-cards`: search, import, normalize, audit, or attach character cards, with compact in-conversation previews for review.
- `tavern-worldbooks`: create, import, audit, or repair lore and worldbooks.
- `tavern-story-profile`: recall stories, manage durable story preferences, synchronize model-aggregated play style and taste to `USER.md`, and project bounded model-generated plot-ledger events into `MEMORY.md`.
- `tavern-continuity`: diagnose or repair compression, dynamic cast state, story_state, runtime_cast, prompts, or generation; always plan before apply for state repair.
- `tavern-ops`: configure models, restart, verify, or localize Liveware.

Use `/opt/data/skills/system/tavern-updater` for version checks, review, installation, and rollback. Never improvise `git pull` or overwrite the runtime or skill directories.

```sh
python3 /opt/data/skills/system/tavern-updater/scripts/update.py check
python3 /opt/data/skills/system/tavern-updater/scripts/update.py review
python3 /opt/data/skills/system/tavern-updater/scripts/update.py report --plan <PLAN_ID>
```

After `report`, show one concise summary and wait for a new explicit approval. Only then run:

```sh
python3 /opt/data/skills/system/tavern-updater/scripts/update.py apply --plan <PLAN_ID> --confirm
```

The updater manages its explicit runtime and official frontend allowlists, exact eight official creative-skill directories, updater, and complete `/opt/data/AGENTS.md` as one transaction. It must preserve custom skill directories, identity/persona files, assets, starter content, `/opt/data/tavern-state`, `/opt/data/config.yaml`, credentials, sessions, and every unlisted path. For legacy versions without their own stable Release, use only a matching historical runtime baseline bundled with the latest Release after its version, archive hash, exact allowlist, per-file hashes, and embedded marker all verify. Never derive a baseline from live instance files. A failed validation, restart, health check, or skill-registration check must restore the complete pre-update backup.
