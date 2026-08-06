# AGENTS.md

## Tavern Skills And Updates

Use `/opt/data/skills/creative/tavern/SKILL.md` as the lightweight router. Load only the matching specialist workflow:

- `tavern-world`: recommend, find, import, create, localize, expand, rebuild, or
  repair a complete world, including character cards, worldbooks, Persona, and
  opening, with compact ClawChat previews before approved writes.
- `tavern-world-visuals`: import durable world images and design, apply, inspect, or reset the story stage, top title bar, and right-side panel theme.
- `tavern-story-profile`: recall stories, manage durable story preferences, synchronize model-aggregated play style and taste to `USER.md`, and project bounded model-generated plot-ledger events into `MEMORY.md`.
- `tavern-continuity`: diagnose or repair compression, dynamic cast state, story_state, runtime_cast, prompts, or generation; always plan before apply for state repair.
- `tavern-ops`: configure models, restart, verify, or localize Liveware.

Use `/opt/data/skills/system/tavern-updater` for version checks, review, installation, and rollback. Never improvise `git pull` or overwrite the runtime or skill directories.

```sh
curl -fsSL https://github.com/LoveMaker-art/liveware-tavern/releases/latest/download/install-tavern-updater.sh | sh
```

Always start through this verified Bootstrap, even when `tavern-updater` is
already installed. It refreshes only the updater first, then uses the target
release's own rules to produce `check`, `review`, and `report`. If an old updater
reports an allowlist, schema, or managed-file mismatch, automatically restart
the review through Bootstrap instead of asking the user to choose a recovery
method. Bootstrap review does not update Tavern code, official creative skills,
`AGENTS.md`, or user data.

After its `report`, show one concise summary and wait for a new explicit approval. Only then run:

```sh
python3 /opt/data/skills/system/tavern-updater/scripts/update.py apply --plan <PLAN_ID> --confirm
```

The updater manages its explicit runtime and official frontend allowlists, exact
six official creative-skill directories, updater, and complete
`/opt/data/AGENTS.md` as one transaction. During the v1.23 migration it deletes
obsolete `tavern-cards` and `tavern-worldbooks` directories after their workflows
move into `tavern-world`; they are never installed, registered, or retained as
disabled skills. A transaction copy may exist only until rollback is no longer
needed. It must preserve custom skill
directories, identity/persona files, assets, starter content,
`/opt/data/tavern-state`, `/opt/data/config.yaml`, credentials, sessions, and
every unlisted path. For legacy versions without their own stable Release, use
only a matching historical runtime baseline bundled with the latest Release
after its version, archive hash, exact allowlist, per-file hashes, and embedded
marker all verify. Never derive a baseline from live instance files. A failed
validation, restart, health check, or skill-registration check must restore the
complete pre-update backup.
