# Liveware Tavern

Liveware Tavern is a stateful, multi-character story application for Hermes Agent and ClawChat. It combines reusable character cards, worldbooks, per-world personas, long-story memory, model selection, and a mobile-friendly Liveware console.

## Repository Layout

- `skill/` - Tavern runtime, frontend, Hermes skill, operational scripts, references, and state-free starter assets.
- `updater-skill/` - Independent Hermes skill for verified in-place updates from GitHub Releases.
- `scripts/build_release.py` - Builds the signed-by-hash release assets consumed by the updater.
- `docs/` - Product and implementation notes.

## Data Boundary

Application releases never contain or overwrite instance data. User worlds, cards, worldbooks, stories, model choices, app registration, and identity state live under `/opt/data/tavern-state` on each instance.

Credentials, ClawChat databases, sessions, logs, `.env` files, and `/opt/data/config.yaml` are not part of this repository or release archives.

## Build A Release

```sh
python3 scripts/build_release.py
```

This creates:

```text
dist/manifest.json
dist/tavern-release.tar.gz
```

Create a stable GitHub Release tagged `v<SKILL.md version>` and attach both files. Mirrored instances can then update through `tavern-updater` without rebuilding the image.

## Install The Updater Skill

Place `updater-skill/` at:

```text
/opt/data/skills/system/tavern-updater/
```

The Agent can then check and install a verified stable release after explicit user confirmation.

## License

MIT
